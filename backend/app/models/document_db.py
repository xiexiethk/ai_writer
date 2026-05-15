from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from app.core.database import Base

class Folder(Base):
    __tablename__ = "folders"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("folders.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer)
    upload_time = Column(DateTime(timezone=True), server_default=func.now())
    parsed = Column(Boolean, default=False)
    parse_status = Column(String, default="pending")
    markdown_content = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    chunked = Column(Boolean, default=False)
    vectorize_status = Column(String, default="pending")
    chunk_count = Column(Integer, default=0)
    tags = Column(String, nullable=True)  # 存储为逗号分隔字符串或 JSON
    folder_id = Column(String, ForeignKey("folders.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    file_path = Column(String, nullable=False)
    pdf_path = Column(String, nullable=True)
