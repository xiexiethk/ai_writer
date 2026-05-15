"""
混合检索问答 API - 支持多用户隔离
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid

from app.services.hybrid_rag_service import hybrid_rag_service
from app.api.auth import get_current_user
from app.models.user import User
from app.core.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.conversation import conversation_storage

router = APIRouter()

class HybridQuestionRequest(BaseModel):
    question: str
    folderId: Optional[str] = None
    folderIds: Optional[List[str]] = None
    documentIds: Optional[List[str]] = None
    conversationId: Optional[str] = None
    taskId: Optional[str] = None

class CreateConversationRequest(BaseModel):
    """创建对话请求"""
    folderId: str = Field(..., description="知识库ID")
    firstQuestion: str = Field(..., description="第一个问题")
    taskId: Optional[str] = Field(None, description="任务ID，用于停止生成")

class StopGenerationRequest(BaseModel):
    """停止生成请求"""
    taskId: str = Field(..., description="任务ID")

@router.post("/ask")
async def ask_question(
    request: HybridQuestionRequest,
    current_user: User = Depends(get_current_user)
):
    """带隔离的提问接口"""
    try:
        conversation_history = None
        if request.conversationId:
            conversation = conversation_storage.get_conversation(
                request.conversationId,
                user_id=current_user.id,
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="对话不存在")
            conversation_history = conversation.get("messages", [])

        result = await hybrid_rag_service.answer_question(
            query=request.question,
            user_id=current_user.id,
            document_ids=request.documentIds,
            folder_id=request.folderId,
            folder_ids=request.folderIds,
            conversation_history=conversation_history,
            task_id=request.taskId,
        )

        if request.conversationId:
            conversation_storage.add_message(
                request.conversationId,
                "user",
                request.question,
                user_id=current_user.id,
            )
            conversation_storage.add_message(
                request.conversationId,
                "assistant",
                result["answer"],
                result.get("sources", []),
                user_id=current_user.id,
            )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/search")
async def search_only(
    request: HybridQuestionRequest,
    current_user: User = Depends(get_current_user)
):
    """带隔离的搜索接口"""
    try:
        results = await hybrid_rag_service.hybrid_search(
            query=request.question,
            user_id=current_user.id,
            document_ids=request.documentIds,
            folder_id=request.folderId,
            folder_ids=request.folderIds,
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conversations")
async def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    创建对话

    创建新的对话并自动回答第一个问题
    """
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
        result = await hybrid_rag_service.answer_question(
            query=request.firstQuestion,
            user_id=current_user.id,
            folder_id=request.folderId,
        )

        # 保存助手回答
        conversation_storage.add_message(
            conversation["id"],
            "assistant",
            result["answer"],
            result.get("sources", []),
            user_id=current_user.id,
        )

        return {
            "conversationId": conversation["id"],
            "answer": result["answer"],
            "sources": result.get("sources", [])
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
        conversation = conversation_storage.get_conversation(conversation_id, user_id=current_user.id)
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
        success = conversation_storage.delete_conversation(conversation_id, user_id=current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="对话不存在")

        return {"message": "删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除对话失败: {str(e)}")

@router.post("/stop")
async def stop_generation(request: StopGenerationRequest):
    """
    停止生成任务
    """
    try:
        from app.services.task_manager import task_manager
        success = task_manager.stop_task(request.taskId)
        if success:
            return {"message": "任务已停止", "taskId": request.taskId}
        else:
            return {"message": "任务已停止或已完成", "taskId": request.taskId}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止任务失败: {str(e)}")
