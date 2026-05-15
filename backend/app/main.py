from typing import Optional
"""
AI Writer Backend - FastAPI 主入口
"""
from fastapi import FastAPI, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy import and_
import uvicorn
from pathlib import Path
import sys

from app.api import documents, folders, chat, hybrid_chat, agent_chat, auth, document_projects
from app.api.auth import get_current_user, get_user_by_token
from app.models.user import User
from app.core.config import settings
from app.services.llm_gateway import resolve_chat_provider, resolve_embedding_provider
from app.core.database import engine, Base

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    print(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} 启动中...")

    # 创建数据库表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✓ 数据库已同步")

    # 初始化 embedding 服务维度
    if settings.SKIP_EMBEDDING_WARMUP:
        print("↷ 已跳过 embedding 启动预热")
    else:
        try:
            from app.services.embedding import embedding_service
            print("📊 初始化 embedding 服务...")
            # 触发一次 embedding 以获取正确的维度
            test_vector = embedding_service.encode_single("初始化")
            print(f"✓ Embedding 服务已初始化，向量维度: {embedding_service.dimension}")
        except Exception as e:
            print(f"⚠️  Embedding 服务初始化失败: {e}")

    yield
    # 关闭时清理
    print("👋 应用关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI Writer Backend API - 集成 MinerU 文档解析",
    lifespan=lifespan,
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(folders.router, prefix="/api/folders", tags=["folders"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(hybrid_chat.router, prefix="/api/hybrid", tags=["hybrid"])
app.include_router(agent_chat.router, prefix="/api/agent", tags=["agent"])
app.include_router(document_projects.router, prefix="/api/document-projects", tags=["document-projects"])

from openwps_server.app import create_app as create_openwps_app

app.mount("/openwps", create_openwps_app())

# 挂载静态文件服务（用于 KaTeX 等本地资源）
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    print(f"✓ 静态文件服务已挂载: {static_dir}")
else:
    print(f"⚠ 静态文件目录不存在: {static_dir}")

# 挂载图片目录（用于文档图片预览）
images_dir = Path(settings.UPLOAD_DIR).parent / "data" / "images"
if images_dir.exists():
    app.mount("/api/documents/images", StaticFiles(directory=str(images_dir)), name="images")
    print(f"✓ 图片服务已挂载: {images_dir}")
else:
    print(f"⚠ 图片目录不存在: {images_dir}")

# 挂载 parsed_output 目录（用于文档图片预览）
parsed_output_dir = Path(settings.MINERU_OUTPUT_DIR)
if parsed_output_dir.exists():
    app.mount("/api/parsed-output", StaticFiles(directory=str(parsed_output_dir)), name="parsed_output")
    print(f"✓ parsed_output 服务已挂载: {parsed_output_dir}")
else:
    print(f"⚠ parsed_output 目录不存在: {parsed_output_dir}")


@app.get("/")
async def root():
    """根路径"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "modelProvider": settings.MODEL_PROVIDER,
        "chatProvider": resolve_chat_provider(),
        "embeddingProvider": resolve_embedding_provider(),
    }

@app.get("/api/documents/{document_id}/images/{image_name}")
async def get_document_image(
    document_id: str,
    image_name: str,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    """获取文档解析后的图片"""
    from fastapi.responses import FileResponse

    # 获取文档信息
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.document_db import Document

    async with AsyncSessionLocal() as session:
        raw_token = token
        if not raw_token and authorization and authorization.startswith("Bearer "):
            raw_token = authorization.removeprefix("Bearer ").strip()

        if not raw_token:
            raise HTTPException(status_code=401, detail="无法验证凭据")

        current_user = await get_user_by_token(raw_token, session)

        result = await session.execute(
            select(Document).where(
                and_(Document.id == document_id, Document.user_id == current_user.id)
            )
        )
        doc = result.scalars().first()
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")

        backend_root = Path(__file__).parent.parent
        parsed_root = (backend_root / settings.MINERU_OUTPUT_DIR).resolve()
        source_path = Path(doc.pdf_path or doc.file_path)
        if not source_path.is_absolute():
            source_path = (backend_root / source_path).resolve()

        candidate_dirs = []
        exact_dir = parsed_root / source_path.stem
        if exact_dir.exists():
            candidate_dirs.append(exact_dir)

        if parsed_root.exists():
            for child in parsed_root.iterdir():
                if not child.is_dir() or child in candidate_dirs:
                    continue
                if (
                    child.name == source_path.stem
                    or child.name.startswith(source_path.stem)
                    or source_path.stem.startswith(child.name)
                    or child.name.startswith(source_path.stem[:15])
                ):
                    candidate_dirs.append(child)

        for candidate_dir in candidate_dirs:
            for relative_path in (
                Path("auto") / "images" / image_name,
                Path("vlm") / "images" / image_name,
                Path("images") / image_name,
            ):
                image_path = candidate_dir / relative_path
                if image_path.exists():
                    return FileResponse(image_path)

            for image_path in candidate_dir.rglob(image_name):
                if image_path.is_file() and image_path.parent.name == "images":
                    return FileResponse(image_path)

        raise HTTPException(status_code=404, detail="图片不存在")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
