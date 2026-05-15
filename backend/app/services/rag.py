"""
RAG 问答服务
整合向量检索、重排序和LLM生成
"""
import logging
from typing import List, Dict, Optional
import numpy as np
import threading
import asyncio
from datetime import datetime

from app.services.llm_gateway import chat_completion_async, resolve_chat_model, resolve_chat_provider
from app.services.embedding import embedding_service
from app.services.vector_store import vector_store
from app.models.document import storage

logger = logging.getLogger(__name__)


class TaskManager:
    """任务管理器，用于跟踪和停止正在运行的任务"""

    def __init__(self):
        self.active_tasks: Dict[str, Dict] = {}  # task_id -> task_info
        self.lock = threading.Lock()

    def create_task(self, task_id: str) -> bool:
        """创建新任务"""
        with self.lock:
            if task_id in self.active_tasks:
                return False
            self.active_tasks[task_id] = {
                "status": "running",
                "created_at": datetime.now().isoformat()
            }
            return True

    def stop_task(self, task_id: str) -> bool:
        """停止任务并释放显存"""
        with self.lock:
            if task_id in self.active_tasks:
                self.active_tasks[task_id]["status"] = "stopped"
                # 释放显存
                try:
                    logger.info(f"任务 {task_id} 已停止")
                except Exception as e:
                    logger.warning(f"释放显存失败: {e}")
                return True
            return False

    def is_task_stopped(self, task_id: str) -> bool:
        """检查任务是否被停止"""
        with self.lock:
            task = self.active_tasks.get(task_id)
            return task and task.get("status") == "stopped"

    def remove_task(self, task_id: str):
        """移除任务"""
        with self.lock:
            self.active_tasks.pop(task_id, None)


# 全局任务管理器
task_manager = TaskManager()


class RAGService:
    """RAG 问答服务"""

    def __init__(
        self,
        provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        reranker_model: str = "dengcao/Qwen3-Reranker-8B:Q3_K_M",
        top_k: int = 10,  # 检索的文档数量
        rerank_top_k: int = 5  # 重排序后保留的文档数量
    ):
        self.provider = resolve_chat_provider(provider)
        self.llm_model = resolve_chat_model(self.provider, llm_model)
        self.reranker_model = reranker_model
        self.top_k = top_k
        self.rerank_top_k = rerank_top_k

    def search_relevant_chunks(
        self,
        query: str,
        document_id: str = None,
        document_ids: List[str] = None,
        top_k: int = None
    ) -> List[Dict]:
        """
        搜索相关文档块

        Args:
            query: 查询文本
            document_id: 单个文档ID
            document_ids: 多个文档ID列表（用于知识库级别搜索）
            top_k: 返回结果数量

        Returns:
            相关文档块列表
        """
        if not vector_store.connected:
            vector_store.connect()

        # 生成查询向量
        query_vector = embedding_service.encode_single(query)

        # 向量搜索
        top_k = top_k or self.top_k

        # 如果提供了多个文档ID，分别搜索后合并
        if document_ids:
            all_results = []
            per_doc_k = max(top_k // len(document_ids), 3)  # 每个文档至少返回3个
            for doc_id in document_ids:
                try:
                    results = vector_store.search(query_vector, per_doc_k, doc_id)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"搜索文档 {doc_id} 失败: {e}")
                    continue

            # 按score排序并返回top_k
            all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
            return all_results[:top_k]
        else:
            # 单个文档搜索
            results = vector_store.search(query_vector, top_k, document_id)
            return results

    def rerank_chunks(
        self,
        query: str,
        chunks: List[Dict],
        top_k: int = None
    ) -> List[Dict]:
        """
        使用 Reranker 对检索结果进行重排序

        Args:
            query: 查询文本
            chunks: 检索到的文档块
            top_k: 保留的文档数量

        Returns:
            重排序后的文档块
        """
        if not chunks:
            return []

        # 直接使用向量搜索的 score，不重新计算
        # chunks 已经按 score 排序了，直接返回 top_k
        top_k = top_k or self.rerank_top_k
        logger.info(f"使用已有的向量相似度分数，返回 top {top_k}")
        return chunks[:top_k]

    async def generate_answer(
        self,
        query: str,
        context_chunks: List[Dict],
        conversation_history: List[Dict] = None,
        task_id: str = None
    ) -> str:
        """
        使用 LLM 生成回答

        Args:
            query: 用户问题
            context_chunks: 相关文档块
            conversation_history: 对话历史
            task_id: 任务ID，用于停止任务

        Returns:
            生成的回答
        """
        # 构建上下文
        context = self._build_context(query, context_chunks)

        # 构建提示词
        prompt = self._build_prompt(query, context, conversation_history)

        try:
            # 调用在线聊天模型生成回答
            # 使用较短的超时时间，以便可以快速检查停止状态
            answer = await chat_completion_async(
                provider=self.provider,
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个专业的AI助手，擅长回答问题并引用相关资料。"
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                top_p=0.9,
                max_tokens=2000,
                timeout=120.0,
            )
            return answer

        except Exception as e:
            logger.error(f"生成回答失败: {e}")
            raise

    def _build_context(self, query: str, chunks: List[Dict]) -> str:
        """构建上下文"""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            title = chunk.get("title", "无标题")
            content = chunk.get("content", "")
            context_parts.append(f"[引用{i}] {title}\n{content}")

        return "\n\n".join(context_parts)

    def _build_prompt(
        self,
        query: str,
        context: str,
        conversation_history: List[Dict] = None
    ) -> str:
        """构建提示词"""
        prompt = f"""请根据以下参考资料回答问题。

参考资料：
{context}

问题：{query}

要求：
1. 基于参考资料回答问题
2. 如果参考资料中没有相关信息，请明确说明
3. 回答时请标注引用的资料编号，如 [引用1]
4. 回答要准确、清晰、有条理

回答："""
        return prompt

    def _get_document_names(self, chunks: List[Dict]) -> Dict[str, str]:
        """
        获取文档名称映射

        Args:
            chunks: 文档块列表

        Returns:
            文档ID到文档名称的映射字典
        """
        doc_ids = set()
        for chunk in chunks:
            doc_id = chunk.get("document_id")
            if doc_id:
                doc_ids.add(doc_id)

        doc_names = {}
        for doc_id in doc_ids:
            try:
                doc = storage.get_document(doc_id)
                if doc:
                    doc_names[doc_id] = doc.get("title", "未知文档")
                else:
                    doc_names[doc_id] = "未知文档"
            except Exception as e:
                logger.warning(f"获取文档 {doc_id} 名称失败: {e}")
                doc_names[doc_id] = "未知文档"

        return doc_names

    async def answer_question(
        self,
        query: str,
        document_id: str = None,
        document_ids: List[str] = None,
        conversation_id: str = None,
        conversation_history: List[Dict] = None,
        task_id: str = None
    ) -> Dict:
        """
        完整的 RAG 问答流程

        Args:
            query: 用户问题
            document_id: 单个文档ID
            document_ids: 多个文档ID列表（用于知识库级别搜索）
            conversation_id: 对话ID（用于获取历史）
            conversation_history: 对话历史
            task_id: 任务ID，用于停止任务

        Returns:
            回答结果，包含答案和引用的文档块
        """
        try:
            # 检查任务是否被停止
            if task_id and task_manager.is_task_stopped(task_id):
                logger.info(f"任务 {task_id} 已被停止")
                raise Exception("任务已被用户停止")

            # 1. 检索相关文档
            logger.info(f"开始检索相关文档，查询: {query}")
            retrieved_chunks = await asyncio.to_thread(
                self.search_relevant_chunks,
                query,
                document_id,
                document_ids,
            )
            logger.info(f"检索到 {len(retrieved_chunks)} 个相关文档块")

            # 检查任务是否被停止
            if task_id and task_manager.is_task_stopped(task_id):
                logger.info(f"任务 {task_id} 已被停止")
                raise Exception("任务已被用户停止")

            # 2. 重排序
            reranked_chunks = await asyncio.to_thread(self.rerank_chunks, query, retrieved_chunks)
            logger.info(f"重排序后保留 {len(reranked_chunks)} 个文档块")

            # 3. 生成回答
            logger.info("开始生成回答")
            answer = await self.generate_answer(query, reranked_chunks, conversation_history, task_id)
            logger.info("回答生成完成")

            # 4. 返回结果（包含引用的文档块）
            # 获取文档名称映射
            doc_names = await asyncio.to_thread(self._get_document_names, reranked_chunks)

            # 清理任务
            if task_id:
                task_manager.remove_task(task_id)

            return {
                "answer": answer,
                "sources": [
                    {
                        "id": chunk.get("id"),
                        "document_id": chunk.get("document_id"),
                        "document_name": doc_names.get(chunk.get("document_id"), "未知文档"),
                        "title": chunk.get("title"),
                        "content": chunk.get("content"),
                        "score": chunk.get("score", 0)
                    }
                    for chunk in reranked_chunks
                ]
            }

        except Exception as e:
            # 清理任务
            if task_id:
                task_manager.remove_task(task_id)
            logger.error(f"RAG 问答失败: {e}")
            raise


# 全局 RAG 服务实例
rag_service = RAGService()
