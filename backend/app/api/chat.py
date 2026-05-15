"""
问答相关 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from sqlalchemy import select

from app.api.auth import get_current_user
from app.core.database import AsyncSessionLocal
from app.models.conversation import conversation_storage
from app.models.document_db import Document
from app.models.user import User
from app.services.rag import rag_service, task_manager

router = APIRouter()


class QuestionRequest(BaseModel):
    """提问请求"""
    question: str = Field(..., description="问题内容")
    documentId: Optional[str] = Field(None, description="文档ID（已弃用，使用folderId）")
    folderId: Optional[str] = Field(None, description="知识库ID（已弃用，使用folderIds）")
    folderIds: Optional[List[str]] = Field(None, description="知识库ID列表（支持多个知识库）")
    documentIds: Optional[List[str]] = Field(None, description="文档ID列表（支持跨知识库选择文档）")
    conversationId: Optional[str] = Field(None, description="对话ID")
    taskId: Optional[str] = Field(None, description="任务ID，用于停止生成")


class AnswerResponse(BaseModel):
    """回答响应"""
    answer: str = Field(..., description="回答内容")
    sources: List[dict] = Field(default_factory=list, description="引用的文档块")


@router.post("/ask")
async def ask_question(
    request: QuestionRequest,
    current_user: User = Depends(get_current_user)
):
    """
    提问（RAG 问答）

    基于知识库内容回答问题，使用 RAG 技术检索相关资料并生成回答

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
            if conversation:
                conversation_history = conversation.get("messages", [])

        # 确定要使用的文档ID列表
        document_ids = None

        # 优先级1：直接指定文档ID列表
        if request.documentIds:
            document_ids = await get_authorized_document_ids(request.documentIds, current_user.id)
        # 优先级2：指定多个知识库
        elif request.folderIds:
            document_ids = await get_document_ids_from_folders(request.folderIds, current_user.id)
        # 优先级3：指定单个知识库（向后兼容）
        elif request.folderId:
            document_ids = await get_document_ids(request.folderId, current_user.id)

        # 执行 RAG 问答
        result = await rag_service.answer_question(
            query=request.question,
            document_id=request.documentId,
            document_ids=document_ids,
            conversation_id=request.conversationId,
            conversation_history=conversation_history,
            task_id=task_id
        )

        # 如果有对话ID，保存消息
        if request.conversationId:
            # 保存用户消息
            conversation_storage.add_message(
                request.conversationId,
                "user",
                request.question,
                user_id=current_user.id
            )

            # 保存助手消息
            conversation_storage.add_message(
                request.conversationId,
                "assistant",
                result["answer"],
                result["sources"],
                user_id=current_user.id
            )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"问答失败: {str(e)}")


async def get_document_ids(folder_id: str, user_id: int) -> Optional[List[str]]:
    """获取当前用户在知识库下的所有已解析文档ID"""
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
    """获取当前用户在多个知识库下的所有已解析文档ID"""
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


class CreateConversationRequest(BaseModel):
    """创建对话请求"""
    folderId: str = Field(..., description="知识库ID")
    firstQuestion: str = Field(..., description="第一个问题")
    taskId: Optional[str] = Field(None, description="任务ID，用于停止生成")


@router.post("/conversations")
async def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    创建对话

    创建新的对话并自动回答第一个问题
    """
    # 创建任务
    task_id = request.taskId or str(uuid.uuid4())
    task_manager.create_task(task_id)

    try:
        # 创建对话（使用第一个问题作为标题）
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

        # 回答问题
        result = await rag_service.answer_question(
            query=request.firstQuestion,
            document_ids=await get_document_ids(request.folderId, current_user.id),
            conversation_id=conversation["id"],
            conversation_history=None,
            task_id=task_id
        )

        # 保存助手回答
        conversation_storage.add_message(
            conversation["id"],
            "assistant",
            result["answer"],
            result["sources"],
            user_id=current_user.id
        )

        return {
            "conversationId": conversation["id"],
            "answer": result["answer"],
            "sources": result["sources"]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建对话失败: {str(e)}")


@router.get("/conversations")
async def list_conversations(
    folderId: str = Query(..., description="知识库ID"),
    limit: int = Query(20, description="返回数量"),
    current_user: User = Depends(get_current_user)
):
    """
    获取对话列表

    获取指定知识库的所有对话
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
        raise HTTPException(status_code=500, detail=f"获取对话列表失败: {str(e)}")


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    获取对话详情

    获取对话的所有消息历史
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
        raise HTTPException(status_code=500, detail=f"获取对话失败: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    删除对话
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
        raise HTTPException(status_code=500, detail=f"删除对话失败: {str(e)}")


class StopGenerationRequest(BaseModel):
    """停止生成请求"""
    taskId: str = Field(..., description="任务ID")


@router.post("/stop")
async def stop_generation(request: StopGenerationRequest):
    """
    停止生成任务

    停止指定的问答生成任务并释放资源
    """
    try:
        success = task_manager.stop_task(request.taskId)
        if success:
            return {"message": "任务已停止", "taskId": request.taskId}
        else:
            # 任务不存在可能表示：1) 任务已完成 2) 任务还没开始 3) 任务ID错误
            # 无论是哪种情况，都返回成功，因为任务已经不在运行了
            return {"message": "任务已停止或已完成", "taskId": request.taskId}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止任务失败: {str(e)}")
