import json
import asyncio
import os
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.database import engine, Base, AsyncSessionLocal
from app.models.user import User
from app.models.document_db import Document, Folder

async def migrate():
    # 确保表已创建
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # 1. 创建默认管理员
        result = await db.execute(select(User).where(User.username == "admin"))
        admin = result.scalars().first()
        if not admin:
            # 直接存储一个可预测的哈希，或者如果您有 passlib 的替代方案
            # 这里我们使用一个简单的占位符，随后通过系统修改
            admin = User(
                username="admin",
                email="admin@example.com",
                hashed_password="placeholder_hash_use_reset_password",
                is_superuser=True
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
            print(f"创建管理员用户: admin")
        else:
            print("管理员用户已存在")

        # 2. 读取旧数据
        try:
            with open("data/folders.json", "r", encoding="utf-8") as f:
                old_folders = json.load(f)
            with open("data/documents.json", "r", encoding="utf-8") as f:
                old_docs = json.load(f)
        except Exception as e:
            print(f"读取旧数据失败: {e}")
            return

        # 3. 迁移文件夹
        folder_count = 0
        for of in old_folders:
            res = await db.execute(select(Folder).where(Folder.id == of["id"]))
            if not res.scalars().first():
                new_f = Folder(
                    id=of["id"],
                    name=of["name"],
                    parent_id=of["parentId"] if of["parentId"] != "root" and of["parentId"] is not None else None,
                    user_id=admin.id,
                    created_at=datetime.fromisoformat(of["createdAt"]) if "createdAt" in of else datetime.now()
                )
                db.add(new_f)
                folder_count += 1
        
        await db.commit()
        print(f"成功迁移 {folder_count} 个文件夹")

        # 4. 迁移文档
        doc_count = 0
        for od in old_docs:
            res = await db.execute(select(Document).where(Document.id == od["id"]))
            if not res.scalars().first():
                new_d = Document(
                    id=od["id"],
                    title=od["title"],
                    file_name=od["fileName"],
                    file_type=od["fileType"],
                    file_size=od["fileSize"],
                    upload_time=datetime.fromisoformat(od["uploadTime"]) if "uploadTime" in od else datetime.now(),
                    parsed=od.get("parsed", False),
                    parse_status=od.get("parseStatus", "pending"),
                    markdown_content=od.get("markdownContent"),
                    error_message=od.get("errorMessage"),
                    chunked=od.get("chunked", False),
                    vectorize_status=od.get("vectorizeStatus", "pending"),
                    tags=",".join(od.get("tags", [])),
                    folder_id=od["folderId"] if od["folderId"] != "root" and od["folderId"] is not None else None,
                    user_id=admin.id,
                    file_path=od["filePath"],
                    pdf_path=od.get("pdfPath")
                )
                db.add(new_d)
                doc_count += 1
        
        await db.commit()
        print(f"成功迁移 {doc_count} 个文档")

if __name__ == "__main__":
    asyncio.run(migrate())
