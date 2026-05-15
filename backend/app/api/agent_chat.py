"""
Agent RAG 问答相关 API 路由
基于 LangGraph 的 ReAct 模式 Agent RAG 系统
"""
import logging
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from sqlalchemy import select

from app.models.conversation import conversation_storage
from app.services.agent_engine.service import agent_rag_service
from app.services.rag import task_manager  # 复用现有的任务管理器
from app.api.auth import get_current_user
from app.core.database import AsyncSessionLocal
from app.models.document_db import Document
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


def get_agent_service():
    return agent_rag_service


class AgentQuestionRequest(BaseModel):
    """Agent 提问请求"""
    question: str = Field(..., description="问题内容")
    documentId: Optional[str] = Field(None, description="文档ID（已弃用，使用folderId）")
    folderId: Optional[str] = Field(None, description="知识库ID（已弃用，使用folderIds）")
    folderIds: Optional[List[str]] = Field(None, description="知识库ID列表（支持多个知识库）")
    documentIds: Optional[List[str]] = Field(None, description="文档ID列表（支持跨知识库选择文档）")
    conversationId: Optional[str] = Field(None, description="对话ID")
    taskId: Optional[str] = Field(None, description="任务ID，用于停止生成")
    maxIterations: Optional[int] = Field(2, description="最大迭代次数（1-50，默认2）", ge=1, le=50)


class AgentAnswerResponse(BaseModel):
    """Agent 回答响应"""
    answer: str = Field(..., description="回答内容")
    sources: List[dict] = Field(default_factory=list, description="引用的文档块（从 Agent 检索过程中收集）")
    steps: List[dict] = Field(default_factory=list, description="Agent 思考步骤")


@router.post("/ask")
async def ask_question(
    request: AgentQuestionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Agent RAG 提问（RAG 问答）

    基于知识库内容回答问题，使用 ReAct 模式的 Agent 系统进行迭代式搜索和推理

    支持三种模式：
    1. 指定 documentIds：精确选择文档（优先级最高）
    2. 指定 folderIds：选择多个知识库的所有文档
    3. 指定 folderId：选择单个知识库的所有文档（向后兼容）
    """
    # 创建任务
    task_id = request.taskId or str(uuid.uuid4())
    task_manager.create_task(task_id)

    try:
        # 获取对话历史
        conversation_history = None
        if request.conversationId:
            conversation = conversation_storage.get_conversation(
                request.conversationId,
                user_id=current_user.id
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="对话不存在")
            if conversation:
                conversation_history = conversation.get("messages", [])

        # 确定要使用的文档ID列表
        document_ids = None

        # 优先级1：直接指定文档ID列表
        if request.documentIds:
            document_ids = await get_authorized_document_ids(request.documentIds, current_user.id) or []
        # 优先级2：指定多个知识库
        elif request.folderIds:
            document_ids = await get_document_ids_from_folders(request.folderIds, current_user.id) or []
        # 优先级3：指定单个知识库（向后兼容）
        elif request.folderId:
            document_ids = await get_document_ids(request.folderId, current_user.id) or []

        # 执行 Agent RAG 问答
        result = await get_agent_service().ask(
            question=request.question,
            chat_history=conversation_history,
            document_ids=document_ids,
            user_id=current_user.id,
            task_id=task_id,
            max_iterations=request.maxIterations or 2
        )

        # 提取答案、步骤和 sources
        answer = result.get("answer", "")
        steps = result.get("steps", [])
        sources = result.get("sources", [])

        # 如果有对话ID，保存消息
        if request.conversationId:
            # 保存用户消息
            conversation_storage.add_message(
                request.conversationId,
                "user",
                request.question,
                user_id=current_user.id
            )

            # 保存助手消息（包含 sources 和 agent_steps）
            conversation_storage.add_message(
                request.conversationId,
                "assistant",
                answer,
                sources=sources,  # Agent 模式下返回收集到的 sources
                agent_steps=steps,  # Agent 思考步骤
                mode="agent",  # 标记为 Agent 模式
                user_id=current_user.id
            )

        # 调试：记录最终返回的数据
        logger.info(f"API /agent/ask 返回: answer长度={len(answer)}, steps数量={len(steps)}, sources数量={len(sources)}")
        if steps:
            logger.info(f"步骤类型列表: {[s.get('type', 'unknown') for s in steps]}")
        
        return {
            "answer": answer,
            "sources": sources,  # 返回收集到的 sources
            "steps": steps
        }

    except Exception as e:
        if task_id:
            task_manager.remove_task(task_id)
        raise HTTPException(status_code=500, detail=f"Agent RAG 问答失败: {str(e)}")


async def get_document_ids(folder_id: str, user_id: int) -> Optional[List[str]]:
    """获取当前用户在指定知识库下的已解析文档ID"""
    if not folder_id:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document.id).where(
                Document.user_id == user_id,
                Document.parsed == True,
                Document.folder_id == folder_id
            )
        )
        document_ids = [row[0] for row in result.all()]

    return document_ids if document_ids else None


async def get_document_ids_from_folders(folder_ids: List[str], user_id: int) -> Optional[List[str]]:
    """获取当前用户在多个知识库下的已解析文档ID"""
    if not folder_ids:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document.id).where(
                Document.user_id == user_id,
                Document.parsed == True,
                Document.folder_id.in_(folder_ids)
            )
        )
        all_document_ids = [row[0] for row in result.all()]

    return all_document_ids if all_document_ids else None


async def get_authorized_document_ids(document_ids: List[str], user_id: int) -> Optional[List[str]]:
    """过滤出当前用户有权限访问且已解析的文档ID"""
    if not document_ids:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document.id).where(
                Document.user_id == user_id,
                Document.parsed == True,
                Document.id.in_(document_ids)
            )
        )
        authorized_ids = [row[0] for row in result.all()]

    return authorized_ids if authorized_ids else None


class AgentCreateConversationRequest(BaseModel):
    """创建 Agent 对话请求"""
    folderId: str = Field(..., description="知识库ID")
    firstQuestion: str = Field(..., description="第一个问题")
    taskId: Optional[str] = Field(None, description="任务ID，用于停止生成")
    maxIterations: Optional[int] = Field(2, description="最大迭代次数（1-50，默认2）", ge=1, le=50)


@router.post("/conversations")
async def create_conversation(
    request: AgentCreateConversationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    创建 Agent 对话并回答第一个问题
    """
    task_id = request.taskId or str(uuid.uuid4())
    task_manager.create_task(task_id)

    try:
        # 获取文档ID列表
        document_ids = await get_document_ids(request.folderId, current_user.id) or []
        if not document_ids:
            logger.warning(f"知识库 {request.folderId} 中没有文档")
            # 即使没有文档，也允许创建对话，Agent 会尝试回答

        # 创建对话
        first_message = {
            "role": "user",
            "content": request.firstQuestion
        }
        conversation = conversation_storage.create_conversation(
            title=request.firstQuestion[:30],
            folder_id=request.folderId,
            first_message=first_message,
            user_id=current_user.id
        )

        # 执行 Agent RAG 问答
        result = await get_agent_service().ask(
            question=request.firstQuestion,
            chat_history=None,
            document_ids=document_ids,
            user_id=current_user.id,
            task_id=task_id,
            max_iterations=request.maxIterations or 2
        )

        # 提取答案、步骤和 sources
        answer = result.get("answer", "")
        steps = result.get("steps", [])
        sources = result.get("sources", [])
        
        # 保存助手消息（包含 sources 和 agent_steps）
        conversation_storage.add_message(
            conversation["id"],
            "assistant",
            answer,
            sources=sources,
            agent_steps=steps,  # Agent 思考步骤
            mode="agent",  # 标记为 Agent 模式
            user_id=current_user.id
        )

        return {
            "conversationId": conversation["id"],
            "answer": answer,
            "sources": result.get("sources", []),
            "steps": steps
        }
    except Exception as e:
        if task_id:
            task_manager.remove_task(task_id)
        import traceback
        error_detail = f"创建 Agent 对话失败: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_detail)
        raise HTTPException(status_code=500, detail=f"创建 Agent 对话失败: {str(e)}")


@router.get("/conversations")
async def list_conversations(
    folderId: str = Query(..., description="知识库ID"),
    limit: int = Query(20, description="返回数量"),
    current_user: User = Depends(get_current_user)
):
    """
    获取 Agent 对话列表
    """
    try:
        conversations = conversation_storage.list_conversations(
            folder_id=folderId,
            limit=limit,
            user_id=current_user.id
        )
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 Agent 对话列表失败: {str(e)}")


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取 Agent 对话详情
    """
    try:
        conversation = conversation_storage.get_conversation(
            conversation_id,
            user_id=current_user.id
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="对话不存在")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取 Agent 对话失败: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除 Agent 对话
    """
    try:
        success = conversation_storage.delete_conversation(
            conversation_id,
            user_id=current_user.id
        )
        if not success:
            raise HTTPException(status_code=404, detail="对话不存在")
        return {"message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除 Agent 对话失败: {str(e)}")


class AgentStopGenerationRequest(BaseModel):
    """停止生成请求"""
    taskId: str = Field(..., description="任务ID")


@router.post("/stop")
async def stop_generation(request: AgentStopGenerationRequest):
    """
    停止 Agent 生成
    """
    try:
        success = task_manager.stop_task(request.taskId)
        if success:
            return {"message": "任务已停止", "taskId": request.taskId}
        else:
            return {"message": "任务已停止或已完成", "taskId": request.taskId}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止任务失败: {str(e)}")
