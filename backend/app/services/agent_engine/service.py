"""
Agent RAG Engine - 服务入口
AgentRAGService 类，集成所有组件
"""
import logging
import os
from typing import List, Dict, Optional
from sqlalchemy import select
from langchain_core.messages import HumanMessage, AIMessage

from app.services.agent_engine.llm import create_chat_llm
from app.services.llm_gateway import resolve_chat_model, resolve_chat_provider, strip_thinking_content
from app.services.agent_engine.graph import build_agent_graph
from app.services.agent_engine.state import AgentState
from app.core.database import AsyncSessionLocal
from app.models.document_db import Document

logger = logging.getLogger(__name__)


class AgentRAGService:
    """
    Agent RAG 服务
    
    基于 LangGraph 的 ReAct 模式 Agent RAG 系统
    支持多工具和迭代式搜索
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7
    ):
        """
        初始化 Agent RAG 服务
        
        Args:
            model: 模型名称
            provider: 模型提供方
            base_url: 模型服务地址
            temperature: LLM 温度参数
        """
        self.provider = resolve_chat_provider(provider)
        self.model = resolve_chat_model(self.provider, model)
        self.base_url = base_url
        self.temperature = temperature
        
        # 创建 LLM 实例
        self.llm = create_chat_llm(
            model=self.model,
            provider=self.provider,
            base_url=base_url,
            temperature=temperature
        )
        
        # 构建图
        self.app = build_agent_graph(self.llm)
        
        logger.info(f"Agent RAG 服务初始化完成: {self.provider} / {self.model} @ {base_url}")
    
    async def ask(
        self,
        question: str,
        chat_history: Optional[List[Dict]] = None,
        document_ids: Optional[List[str]] = None,
        user_id: Optional[int] = None,
        task_id: Optional[str] = None,
        max_iterations: int = 2
    ) -> Dict:
        """
        处理用户问题，返回答案和思考步骤
        
        Args:
            question: 用户问题
            chat_history: 对话历史，格式为 [{"role": "user", "content": "..."}, ...]
            document_ids: 限制搜索范围的文档ID列表
            task_id: 任务ID（用于任务停止检查）
            max_iterations: 最大检索次数（默认 2，表示最多执行几次搜索，不是 LangGraph 的递归步数）
        
        Returns:
            包含 answer 和 steps 的字典
        """
        try:
            # 1. 转换对话历史为 LangChain 消息格式
            lc_messages = []
            if chat_history:
                for msg in chat_history:
                    role = msg.get("role")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        lc_messages.append(HumanMessage(content=content))
                    elif role == "assistant":
                        lc_messages.append(AIMessage(content=content))
            
            # 添加当前问题
            lc_messages.append(HumanMessage(content=question))
            
            # 2. 构建初始 state（初始化 steps 为空列表）
            # max_iterations 现在表示最大检索次数（搜索工具调用次数），而不是 LangGraph 的递归步数
            # 设置一个足够大的 recursion_limit（检索次数 * 5 + 10），确保有足够的步数完成所有检索和生成答案
            max_search_count = max(1, min(max_iterations, 20))  # 检索次数限制在 1-20 之间
            recursion_limit = max_search_count * 5 + 10  # 每次检索大约需要 3-4 步，加上缓冲
            
            input_state: AgentState = {
                "messages": lc_messages,
                "user_id": user_id,
                "original_question": question,
                "document_ids": document_ids,
                "task_id": task_id,
                "max_search_count": max_search_count,  # 最大检索次数
                "search_count": 0,  # 当前检索次数
                "steps": [],
                "sources": [],
                "pending_tool_name": None,
                "pending_tool_input": None,
                "final_answer": None,
            }
            
            logger.info(f"Agent 启动：最大检索次数={max_search_count}，LangGraph 递归限制={recursion_limit}")
            
            # 3. 调用图
            result = await self.app.ainvoke(
                input_state,
                config={"recursion_limit": recursion_limit}
            )
            
            # 4. 提取最后一条 AIMessage 的内容
            messages = result.get("messages", [])
            if not messages:
                return {
                    "answer": "未生成回答。",
                    "steps": []
                }
            
            last_message = messages[-1]
            
            # 如果是 AIMessage，提取内容
            if hasattr(last_message, "content"):
                answer = last_message.content
            else:
                answer = str(last_message)
            answer = strip_thinking_content(answer)
            
            # 5. 提取思考步骤
            steps = result.get("steps", [])
            
            # 调试：记录步骤数量
            logger.info(f"提取到的步骤数量: {len(steps)}")
            if steps:
                logger.info(f"步骤类型: {[s.get('type', 'unknown') for s in steps]}")
            
            # 格式化步骤数据（确保所有字段都存在）
            formatted_steps = []
            for step in steps:
                formatted_step = {
                    "type": step.get("type", "unknown"),
                    "content": step.get("content", ""),
                    "tool": step.get("tool"),
                    "status": step.get("status", "success"),
                    "timestamp": step.get("timestamp", 0)
                }
                # 保留 details 字段（如果存在）
                if "details" in step:
                    formatted_step["details"] = step.get("details")
                formatted_steps.append(formatted_step)
            
            # 调试：记录格式化后的步骤数量
            logger.info(f"格式化后的步骤数量: {len(formatted_steps)}")
            
            # 6. 提取和格式化 sources
            raw_sources = result.get("sources", [])
            formatted_sources = []
            
            if raw_sources:
                doc_ids = set()
                for source in raw_sources:
                    doc_id = source.get("document_id")
                    if doc_id:
                        doc_ids.add(doc_id)
                
                doc_names = {}
                if doc_ids:
                    try:
                        async with AsyncSessionLocal() as db:
                            query = select(Document.id, Document.title).where(Document.id.in_(list(doc_ids)))
                            if user_id is not None:
                                query = query.where(Document.user_id == user_id)
                            rows = await db.execute(query)
                            doc_names = {row[0]: row[1] for row in rows.all()}
                    except Exception as e:
                        logger.warning(f"批量获取 Agent sources 文档名称失败: {e}")
                        doc_names = {}
                
                # 格式化 sources
                for source in raw_sources:
                    doc_id = source.get("document_id", "")
                    formatted_source = {
                        "id": str(source.get("id", "")),
                        "document_id": doc_id,
                        "document_name": doc_names.get(doc_id, "未知文档"),
                        "title": source.get("title", ""),
                        "content": source.get("content", ""),
                        "score": source.get("score", 0.0),
                        "chunk_index": source.get("chunk_index", 0),
                        "level": source.get("level", 0)
                    }
                    formatted_sources.append(formatted_source)
            
            logger.info(f"Agent RAG 回答生成完成，长度: {len(answer)}, 步骤数: {len(formatted_steps)}, 来源数: {len(formatted_sources)}")
            return {
                "answer": answer,
                "steps": formatted_steps,
                "sources": formatted_sources
            }
        
        except Exception as e:
            logger.error(f"Agent RAG 问答失败: {e}")
            raise


def create_agent_rag_service(
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.7,
) -> AgentRAGService:
    return AgentRAGService(
        provider=provider or os.getenv("AGENT_CHAT_PROVIDER") or "deepseek",
        model=model or os.getenv("AGENT_CHAT_MODEL"),
        base_url=base_url or os.getenv("AGENT_CHAT_BASE_URL"),
        temperature=temperature,
    )


# 创建单例实例（可被环境变量覆盖，方便测试注入）
agent_rag_service = create_agent_rag_service()
