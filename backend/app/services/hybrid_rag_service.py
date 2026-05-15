"""
标准向量表 RAG 问答服务 - 支持多用户数据隔离。
当前强制复用 document_chunks_v2，避免依赖 hybrid_document_chunks_v2。
"""
import logging
import httpx
import asyncio
from typing import List, Dict, Optional
from sqlalchemy.future import select
from app.core.database import AsyncSessionLocal
from app.models.document_db import Document

from app.services.llm_gateway import chat_completion_async, resolve_chat_model, resolve_chat_provider
from app.services.embedding import embedding_service
from app.services.vector_store import vector_store
from app.services.rag import task_manager
from app.services.retrieval_orchestrator import retrieval_orchestrator

logger = logging.getLogger(__name__)

class HybridRAGService:
    """混合检索 RAG 问答服务"""

    def __init__(
        self,
        provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        top_k: int = 10
    ):
        self.provider = resolve_chat_provider(provider)
        self.llm_model = resolve_chat_model(self.provider, llm_model)
        self.top_k = top_k
        self.timeout = httpx.Timeout(300.0, connect=10.0)

    @staticmethod
    def _normalize_history_messages(
        conversation_history: Optional[List[Dict]],
        limit: int = 6,
    ) -> List[Dict]:
        if not conversation_history:
            return []
        normalized: List[Dict] = []
        for item in conversation_history[-limit:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _extract_persistent_style_constraints(
        conversation_history: Optional[List[Dict]],
    ) -> str:
        if not conversation_history:
            return ""

        candidates: List[str] = []
        keywords = (
            "以后",
            "后续",
            "从现在开始",
            "始终",
            "一直",
            "请用",
            "语气",
            "三点",
            "列表",
            "简短",
            "正式",
            "风格",
            "格式",
        )
        for item in conversation_history[-8:]:
            if item.get("role") != "user":
                continue
            content = (item.get("content") or "").strip()
            if content and any(token in content for token in keywords):
                candidates.append(content)
        return "\n".join(candidates[-3:])

    async def hybrid_search(
        self,
        query: str,
        user_id: int,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
        folder_ids: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        mode: str = "qa",
        conversation_history: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """执行带用户隔离的高级轻量检索编排。"""
        if not vector_store.connected:
            vector_store.connect()

        top_k = top_k or self.top_k

        target_doc_ids: List[str] = []
        if document_id:
            target_doc_ids = [document_id]
        elif document_ids:
            target_doc_ids = list(document_ids)
        elif folder_id or folder_ids:
            async with AsyncSessionLocal() as db:
                query_stmt = select(Document.id).where(Document.user_id == user_id, Document.parsed == True)
                if folder_id:
                    query_stmt = query_stmt.where(Document.folder_id == folder_id)
                elif folder_ids:
                    query_stmt = query_stmt.where(Document.folder_id.in_(folder_ids))
                result = await db.execute(query_stmt)
                target_doc_ids = [row[0] for row in result.all()]

        if target_doc_ids:
            unique_doc_ids = list(dict.fromkeys(target_doc_ids))
            orchestrated = await retrieval_orchestrator.retrieve(
                query=query,
                user_id=user_id,
                document_ids=unique_doc_ids,
                mode=mode,
                top_k=top_k,
                conversation_history=conversation_history,
                search_fn=self._search_standard_store,
            )
            logger.info("高级轻量检索完成: strategy=%s, queries=%s, results=%s", orchestrated.selected_strategy, orchestrated.queries, len(orchestrated.chunks))
            return orchestrated.chunks

        logger.warning("标准向量检索缺少显式 document_ids，拒绝执行全库检索")
        return []

    def _search_standard_store(
        self,
        query: str,
        top_k: int,
        document_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        """在标准向量表 document_chunks_v2 上做搜索。"""
        if not vector_store.connected:
            vector_store.connect()

        query_vector = embedding_service.encode_single(query)
        target_doc_ids = list(dict.fromkeys(document_ids or []))
        if not target_doc_ids:
            logger.warning("标准向量检索缺少 document_ids，拒绝执行全库检索")
            return []
        if target_doc_ids:
            all_results: List[Dict] = []
            per_doc_k = max(top_k // max(len(target_doc_ids), 1), 3)
            for doc_id in target_doc_ids:
                try:
                    all_results.extend(vector_store.search(query_vector, per_doc_k, doc_id))
                except Exception as exc:
                    logger.warning("标准向量检索文档 %s 失败: %s", doc_id, exc)
            all_results.sort(key=lambda item: item.get("score", 0.0), reverse=True)
            return all_results[:top_k]

        try:
            return vector_store.search(query_vector, top_k)
        except Exception as exc:
            logger.warning("标准向量检索失败: %s", exc)
            return []

    async def answer_question(
        self,
        query: str,
        user_id: int,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        folder_id: Optional[str] = None,
        folder_ids: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict]] = None,
        task_id: Optional[str] = None
    ) -> Dict:
        """完整的 RAG 问答流程（支持隔离）"""
        try:
            # 1. 检索
            retrieved_chunks = await self.hybrid_search(
                query=query,
                user_id=user_id,
                document_id=document_id,
                document_ids=document_ids,
                folder_id=folder_id,
                folder_ids=folder_ids,
                mode="qa",
                conversation_history=conversation_history,
            )

            # 2. 构建上下文并生成回答
            context = ""
            for i, chunk in enumerate(retrieved_chunks[:5], 1):
                context += f"[引用{i}] {chunk.get('title')}\n{chunk.get('content')}\n\n"

            history_messages = self._normalize_history_messages(conversation_history)
            style_constraints = self._extract_persistent_style_constraints(conversation_history)

            prompt_parts = [
                "请根据以下参考资料回答问题。",
                "",
                "参考资料：",
                context if context else "（当前未检索到明确参考资料，可在必要时基于对话上下文给出保守回答，并明确说明资料不足。）",
            ]
            if style_constraints:
                prompt_parts.extend([
                    "",
                    "用户在前文明确提出的持续约束：",
                    style_constraints,
                ])
            prompt_parts.extend([
                "",
                f"当前问题：{query}",
                "",
                "回答要求：",
                "1. 优先遵循用户前文已提出的风格、格式和长度约束。",
                "2. 如果问题里出现“它”“那”“继续”“简短一点”等指代或延续表达，应结合前文语境理解。",
                "3. 如果参考资料不足，请明确说明，但仍尽量保持用户要求的回答风格。",
                "4. 回答尽量延续当前对话的主题与约束，不要无故重置风格。",
            ])
            prompt = "\n".join(prompt_parts)
            
            messages: List[Dict] = [
                {
                    "role": "system",
                    "content": (
                        "你是一个多轮对话助手。必须保持对用户持续意图、输出格式和语气要求的记忆。"
                    ),
                }
            ]
            messages.extend(history_messages)
            messages.append({"role": "user", "content": prompt})

            answer = await chat_completion_async(
                provider=self.provider,
                model=self.llm_model,
                messages=messages,
                timeout=self.timeout,
            )

            # 3. 获取文档名称 (从数据库获取，确保隔离安全)
            sources = []
            async with AsyncSessionLocal() as db:
                for chunk in retrieved_chunks[:5]:
                    res = await db.execute(select(Document).where(Document.id == chunk['document_id']))
                    doc = res.scalars().first()
                    sources.append({
                        "id": chunk.get("id"),
                        "document_name": doc.title if doc else "未知文档",
                        "content": chunk.get("content"),
                        "score": chunk.get("score")
                    })

            return {"answer": answer, "sources": sources}

        except Exception as e:
            logger.error(f"RAG failed: {e}")
            raise

# 全局实例
hybrid_rag_service = HybridRAGService()
