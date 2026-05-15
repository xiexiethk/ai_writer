"""
文件夹（知识库）相关 API 路由 - 支持多用户数据隔离
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.core.database import get_db
from app.api.auth import get_current_user
from app.models.user import User
from app.models.document_db import Folder
from pydantic import BaseModel

router = APIRouter()

class FolderCreate(BaseModel):
    name: str
    parentId: Optional[str] = None

class FolderUpdate(BaseModel):
    name: str

@router.get("")
async def list_folders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户的文件夹列表"""
    result = await db.execute(select(Folder).where(Folder.user_id == current_user.id))
    folders = result.scalars().all()
    
    # 转换为前端需要的格式
    return [
        {
            "id": f.id,
            "name": f.name,
            "parentId": f.parent_id or "root",
            "createdAt": f.created_at.isoformat()
        }
        for f in folders
    ]

@router.post("")
async def create_folder(
    data: FolderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """创建文件夹"""
    folder_id = str(uuid.uuid4())
    db_folder = Folder(
        id=folder_id,
        name=data.name,
        parent_id=data.parentId if data.parentId != "root" else None,
        user_id=current_user.id
    )
    db.add(db_folder)
    await db.commit()
    await db.refresh(db_folder)
    
    return {
        "id": db_folder.id,
        "name": db_folder.name,
        "parentId": db_folder.parent_id or "root"
    }

@router.delete("/{folder_id}")
async def delete_folder(
    folder_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除文件夹"""
    result = await db.execute(
        select(Folder).where(and_(Folder.id == folder_id, Folder.user_id == current_user.id))
    )
    folder = result.scalars().first()
    if not folder:
        raise HTTPException(status_code=404, detail="文件夹不存在")
    
    await db.delete(folder)
    await db.commit()
    return {"message": "删除成功"}

def update_folder_timestamp(folder_id: str):
    # 暂时保持空，因为迁移到了 DB
    pass
