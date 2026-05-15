"""
文档相关的 Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class FileType(str, Enum):
    """文件类型枚举"""
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"


class ParseStatus(str, Enum):
    """解析状态枚举"""
    PENDING = "pending"
    PARSING = "parsing"
    SUCCESS = "success"
    ERROR = "error"


class DocumentBase(BaseModel):
    """文档基础模型"""
    title: str = Field(..., description="文档标题")
    fileName: str = Field(..., description="文件名")
    fileType: FileType = Field(..., description="文件类型")
    fileSize: int = Field(..., description="文件大小（字节）")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    folderId: str = Field(default="root", description="所属文件夹 ID")


class DocumentCreate(DocumentBase):
    """创建文档"""
    pass


class DocumentUpdate(BaseModel):
    """更新文档"""
    title: Optional[str] = None
    markdownContent: Optional[str] = None
    tags: Optional[List[str]] = None
    folderId: Optional[str] = None


class DocumentResponse(DocumentBase):
    """文档响应"""
    id: str
    uploadTime: datetime
    parsed: bool
    parseStatus: ParseStatus
    chunked: bool = False  # 是否已分块
    vectorizeStatus: Optional[str] = None
    chunkCount: int = 0
    markdownContent: Optional[str] = None
    thumbnail: Optional[str] = None
    errorMessage: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """文档列表响应"""
    documents: List[DocumentResponse]
    total: int


class UploadResponse(BaseModel):
    """上传响应"""
    documentId: str
    fileName: str
    fileSize: int


class ParseResponse(BaseModel):
    """解析响应"""
    documentId: str
    markdownContent: str
    images: List[str] = []


class FolderBase(BaseModel):
    """文件夹基础模型"""
    name: str = Field(..., description="文件夹名称")
    parentId: Optional[str] = Field(None, description="父文件夹 ID")


class FolderCreate(FolderBase):
    """创建文件夹"""
    pass


class FolderUpdate(BaseModel):
    """更新文件夹"""
    name: str = Field(..., description="文件夹名称")


class FolderResponse(FolderBase):
    """文件夹响应"""
    id: str
    createdAt: datetime

    class Config:
        from_attributes = True
