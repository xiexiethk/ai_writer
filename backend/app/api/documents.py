"""
文档相关 API 路由 - 支持多用户数据隔离
"""
import asyncio
import os
import shutil
import base64
import logging
import threading
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, Depends, Header
from fastapi.responses import FileResponse
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, and_, func

from app.core.database import get_db
from app.api.auth import get_current_user, get_user_by_token
from app.models.user import User
from app.models.document_db import Document, Folder
from app.schemas.document import (
    DocumentCreate,
    DocumentUpdate,
    DocumentResponse,
    DocumentListResponse,
    UploadResponse,
    ParseStatus,
)
from app.services.mineru_service import mineru_service
from app.core.config import settings
from app.services.document_converter import document_converter
from app.services.word_converter import word_converter
from app.services.task_manager import task_manager, TaskStatus
from app.services.chunker import chunker
from app.services.embedding import embedding_service
from app.services.vector_store import vector_store

logger = logging.getLogger(__name__)
router = APIRouter()

SUPPORTED_FORMATS = ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "png", "jpg", "jpeg", "txt", "md"]
VECTOR_STORE_WRITE_LOCK = threading.Lock()


def _split_tags(tags: Optional[str]) -> List[str]:
    if not tags:
        return []
    return [tag for tag in (item.strip() for item in tags.split(",")) if tag]


def _is_document_chunked(doc: Document) -> bool:
    status = (doc.vectorize_status or "").lower()
    if status in {"processing", "pending", "error"}:
        return bool(doc.chunked)
    return bool(doc.chunked or status in {"success", "completed"})


def _normalize_vectorize_status(status: Optional[str], chunked: bool) -> str:
    normalized = (status or "").lower()
    if chunked or normalized in {"success", "completed"}:
        return "completed"
    if normalized in {"processing", "error", "pending"}:
        return normalized
    return normalized or "pending"


def _serialize_document(doc: Document) -> Dict[str, Any]:
    chunked = _is_document_chunked(doc)
    return {
        "id": doc.id,
        "title": doc.title,
        "fileName": doc.file_name,
        "fileType": doc.file_type,
        "fileSize": doc.file_size,
        "uploadTime": doc.upload_time.isoformat() if doc.upload_time else None,
        "parsed": bool(doc.parsed),
        "parseStatus": doc.parse_status or "pending",
        "chunked": chunked,
        "vectorizeStatus": _normalize_vectorize_status(doc.vectorize_status, chunked),
        "chunkCount": doc.chunk_count or 0,
        "markdownContent": doc.markdown_content,
        "tags": _split_tags(doc.tags),
        "folderId": doc.folder_id or "root",
        "errorMessage": doc.error_message,
    }


async def _get_user_document(db: AsyncSession, document_id: str, user_id: int) -> Document:
    result = await db.execute(
        select(Document).where(and_(Document.id == document_id, Document.user_id == user_id))
    )
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在或无权访问")
    return doc


def _is_task_active(task_id: str) -> bool:
    task = task_manager.get_task(task_id)
    return bool(task and task.status in {TaskStatus.PENDING, TaskStatus.RUNNING})


def _build_vector_store() -> vector_store.__class__:
    return vector_store.__class__(
        uri=vector_store.uri,
        user=vector_store.user,
        password=vector_store.password,
        collection_name=vector_store.collection_name,
    )


def _vectorize_document_sync(
    document_id: str,
    markdown_content: str,
    warmup_model: bool = True,
) -> int:
    if warmup_model and not embedding_service.warmup():
        raise RuntimeError(f"嵌入模型预热失败: {embedding_service.model_name}")

    chunks_data = chunker.chunk(markdown_content, document_id)
    if not chunks_data:
        raise ValueError("文档分块结果为空")

    texts = [chunk.content for chunk in chunks_data]
    successful_indices, embeddings = embedding_service.encode_with_indices(texts)
    if len(embeddings) == 0:
        raise RuntimeError("没有成功编码任何文本")
    if len(successful_indices) != len(chunks_data):
        raise RuntimeError(
            f"在线向量化未完整成功：共 {len(chunks_data)} 个分块，仅 {len(successful_indices)} 个完成编码"
        )

    successful_chunks = [chunks_data[i] for i in successful_indices]

    chunk_dicts = [
        {
            "id": chunk.id,
            "document_id": document_id,
            "chunk_index": idx,
            "title": chunk.title,
            "content": chunk.content,
            "level": chunk.level,
        }
        for idx, chunk in enumerate(successful_chunks)
    ]

    embeddings_list = embeddings.tolist()
    store = _build_vector_store()

    # Milvus/本地降级存储使用共享状态，写入阶段串行化以避免集合创建和 flush 互相踩踏。
    with VECTOR_STORE_WRITE_LOCK:
        if not store.connected:
            store.connect()

        store.create_collection(
            dimension=embedding_service.dimension,
            drop_existing=False
        )

        try:
            store.delete_document(document_id)
        except Exception as exc:
            logger.warning("删除文档 %s 的旧向量数据失败，继续写入新数据: %s", document_id, exc)

        store.insert_chunks(chunk_dicts, embeddings_list)

    return len(successful_chunks)


async def _execute_vectorize_task(
    document_id: str,
    markdown_content: str,
    mark_processing: bool = False,
    unload_after: bool = True,
    warmup_model: bool = True,
):
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db_session:
        try:
            if mark_processing:
                await db_session.execute(
                    update(Document).where(Document.id == document_id).values(
                        vectorize_status="processing",
                        chunked=False,
                        chunk_count=0,
                        error_message=None,
                    )
                )
                await db_session.commit()

            chunk_count = await asyncio.to_thread(
                _vectorize_document_sync,
                document_id,
                markdown_content,
                warmup_model,
            )
            await db_session.execute(
                update(Document).where(Document.id == document_id).values(
                    vectorize_status="completed",
                    chunked=True,
                    chunk_count=chunk_count,
                    error_message=None,
                )
            )
            await db_session.commit()
            logger.info("向量化任务完成: %s, 共 %s 个分块", document_id, chunk_count)
        except Exception as exc:
            logger.exception("向量化任务失败: %s", document_id)
            await db_session.execute(
                update(Document).where(Document.id == document_id).values(
                    vectorize_status="error",
                    chunked=False,
                    chunk_count=0,
                    error_message=str(exc),
                )
            )
            await db_session.commit()
        finally:
            if unload_after:
                await asyncio.to_thread(embedding_service.unload_model)


async def _execute_parse_task(document_id: str, source_path: str, mark_processing: bool = False):
    from app.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db_session:
        try:
            if mark_processing:
                await db_session.execute(
                    update(Document).where(Document.id == document_id).values(
                        parse_status="parsing",
                        parsed=False,
                        chunked=False,
                        vectorize_status="pending",
                        chunk_count=0,
                        error_message=None,
                    )
                )
                await db_session.commit()

            markdown, error, _ = await mineru_service.parse_pdf(source_path, document_id)
            if error:
                await db_session.execute(
                    update(Document).where(Document.id == document_id).values(
                        parse_status="error",
                        parsed=False,
                        error_message=error,
                    )
                )
            else:
                await db_session.execute(
                    update(Document).where(Document.id == document_id).values(
                        parse_status="success",
                        parsed=True,
                        markdown_content=markdown,
                        chunked=False,
                        vectorize_status="pending",
                        chunk_count=0,
                        error_message=None,
                    )
                )
            await db_session.commit()
        except Exception as exc:
            logger.exception("解析任务失败: %s", document_id)
            await db_session.execute(
                update(Document).where(Document.id == document_id).values(
                    parse_status="error",
                    parsed=False,
                    error_message=str(exc),
                )
            )
            await db_session.commit()


async def _execute_batch_vectorize_task(items: List[tuple[str, str]]):
    concurrency = max(1, settings.BATCH_VECTORIZE_MAX_CONCURRENCY)
    semaphore = asyncio.Semaphore(concurrency)
    warmup_lock = asyncio.Lock()
    warmed_up = False

    async def run_one(document_id: str, markdown_content: str):
        nonlocal warmed_up
        async with semaphore:
            should_warmup = False
            async with warmup_lock:
                if not warmed_up:
                    should_warmup = True
                    warmed_up = True

            await _execute_vectorize_task(
                document_id,
                markdown_content,
                mark_processing=True,
                unload_after=False,
                warmup_model=should_warmup,
            )

    try:
        await asyncio.gather(*(run_one(document_id, markdown_content) for document_id, markdown_content in items))
    finally:
        await asyncio.to_thread(embedding_service.unload_model)


async def _execute_batch_parse_task(items: List[tuple[str, str]]):
    for document_id, source_path in items:
        await _execute_parse_task(document_id, source_path, mark_processing=True)


def _load_document_chunks_sync(document_id: str) -> List[Dict[str, Any]]:
    if not vector_store.connected:
        vector_store.connect()

    chunks = vector_store.get_chunks_by_document(document_id)
    chunks.sort(key=lambda item: item.get("chunk_index", 0))
    return chunks


def _build_preview_chunks(markdown_content: str, document_id: str) -> List[Dict[str, Any]]:
    preview_chunks = chunker.chunk(markdown_content, document_id)
    return [
        {
            "id": chunk.id,
            "document_id": document_id,
            "chunk_index": chunk.chunk_index,
            "title": chunk.title,
            "content": chunk.content,
            "level": chunk.level,
        }
        for chunk in preview_chunks
    ]


async def _get_document_chunks_payload(doc: Document, db: AsyncSession) -> Dict[str, Any]:
    chunks = await asyncio.to_thread(_load_document_chunks_sync, doc.id)

    if not chunks and _normalize_vectorize_status(doc.vectorize_status, _is_document_chunked(doc)) == "completed":
        error_message = "在线向量数据库中未找到该文档分块，请重新执行向量化"
        await db.execute(
            update(Document).where(Document.id == doc.id).values(
                chunked=False,
                vectorize_status="error",
                chunk_count=0,
                error_message=error_message,
            )
        )
        await db.commit()
        raise RuntimeError(error_message)

    if chunks and (
        not _is_document_chunked(doc)
        or (doc.chunk_count or 0) != len(chunks)
        or _normalize_vectorize_status(doc.vectorize_status, True) != "completed"
    ):
        await db.execute(
            update(Document).where(Document.id == doc.id).values(
                chunked=True,
                vectorize_status="completed",
                chunk_count=len(chunks),
                error_message=None,
            )
        )
        await db.commit()

    return {
        "documentId": doc.id,
        "chunkCount": len(chunks),
        "chunks": chunks,
    }

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    folderId: str = Form("root"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """上传文档并绑定到当前用户"""
    file_ext = Path(file.filename).suffix.lower().lstrip(".")
    if file_ext not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {file_ext}")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_id = f"{current_user.id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, file_id)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    pdf_path = file_path
    markdown_content = None
    parsed = False
    parse_status = "pending"

    # Word 转换逻辑保持不变，但结果存入数据库
    if file_ext in ["docx", "doc"]:
        try:
            markdown_content, _ = word_converter.convert_to_markdown(file_path, base_url="/api/documents/images")
            parsed = True
            parse_status = "success"
            converted_pdf, _ = document_converter.convert_to_pdf(file_path, output_dir=settings.UPLOAD_DIR)
            pdf_path = converted_pdf
        except Exception as e:
            logger.error(f"Word conversion failed: {e}")

    elif file_ext != "pdf":
        try:
            pdf_path, _ = document_converter.convert_to_pdf(file_path, output_dir=settings.UPLOAD_DIR)
        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")

    doc_id = str(uuid.uuid4())
    db_doc = Document(
        id=doc_id,
        title=Path(file.filename).stem,
        file_name=file.filename,
        file_type=file_ext,
        file_size=os.path.getsize(file_path),
        file_path=file_path,
        pdf_path=pdf_path,
        parsed=parsed,
        parse_status=parse_status,
        markdown_content=markdown_content,
        folder_id=folderId if folderId != "root" else None,
        user_id=current_user.id
    )

    db.add(db_doc)
    await db.commit()
    await db.refresh(db_doc)

    return UploadResponse(
        documentId=db_doc.id,
        fileName=db_doc.file_name,
        fileSize=db_doc.file_size,
    )

@router.get("", response_model=DocumentListResponse)
async def list_documents(
    folder: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取当前用户的文档列表（数据隔离）"""
    query = select(Document).where(Document.user_id == current_user.id)

    if folder and folder != "root":
        query = query.where(Document.folder_id == folder)
    if search:
        query = query.where(Document.title.contains(search))

    # 获取总数
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query)

    # 分页查询
    result = await db.execute(query.offset(skip).limit(limit))
    docs = result.scalars().all()

    # 转换为 Schema
    doc_responses = [_serialize_document(d) for d in docs]

    return DocumentListResponse(documents=doc_responses, total=total)

@router.get("/{document_id}")
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取单个文档详情（带权限检查）"""
    doc = await _get_user_document(db, document_id, current_user.id)
    return _serialize_document(doc)


@router.put("/{document_id}")
async def update_document(
    document_id: str,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新文档元数据"""
    doc = await _get_user_document(db, document_id, current_user.id)

    if data.title is not None:
        title = data.title.strip()
        if title:
            doc.title = title

    if data.folderId is not None:
        doc.folder_id = None if data.folderId == "root" else data.folderId

    if data.tags is not None:
        doc.tags = ",".join(tag.strip() for tag in data.tags if tag and tag.strip())

    if data.markdownContent is not None:
        doc.markdown_content = data.markdownContent
        doc.parsed = True
        doc.parse_status = "success"
        doc.chunked = False
        doc.vectorize_status = "pending"
        doc.chunk_count = 0
        doc.error_message = None

    await db.commit()
    await db.refresh(doc)
    return _serialize_document(doc)


@router.put("/{document_id}/content")
async def update_document_content(
    document_id: str,
    data: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """更新文档 Markdown 内容，并重置分块状态"""
    if data.markdownContent is None:
        raise HTTPException(status_code=400, detail="markdownContent 不能为空")

    doc = await _get_user_document(db, document_id, current_user.id)
    doc.markdown_content = data.markdownContent
    doc.parsed = True
    doc.parse_status = "success"
    doc.chunked = False
    doc.vectorize_status = "pending"
    doc.chunk_count = 0
    doc.error_message = None

    await db.commit()
    await db.refresh(doc)
    return _serialize_document(doc)

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除文档（带权限检查）"""
    doc = await _get_user_document(db, document_id, current_user.id)

    # 删除物理文件
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    await db.delete(doc)
    await db.commit()
    return {"message": "删除成功"}

@router.post("/{document_id}/parse")
async def parse_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """启动解析（带权限检查）"""
    doc = await _get_user_document(db, document_id, current_user.id)
    doc.parse_status = "parsing"
    doc.parsed = False
    doc.error_message = None
    doc.chunked = False
    doc.vectorize_status = "pending"
    doc.chunk_count = 0
    await db.commit()

    source_path = doc.pdf_path or doc.file_path
    task_id = f"parse_{document_id}"
    await task_manager.submit_task(task_id, _execute_parse_task, document_id, source_path)
    return {"message": "解析任务已提交", "taskId": task_id}


@router.get("/{document_id}/parse/status")
async def get_parse_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文档解析状态"""
    doc = await _get_user_document(db, document_id, current_user.id)
    return {
        "documentId": doc.id,
        "status": doc.parse_status or "pending",
        "parsed": bool(doc.parsed),
    }

@router.get("/{document_id}/pdf-base64")
async def get_document_pdf_base64(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文档PDF的base64编码（带权限检查）"""
    doc = await _get_user_document(db, document_id, current_user.id)

    # 获取PDF文件路径
    pdf_path = doc.pdf_path or doc.file_path
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF文件不存在")

    try:
        with open(pdf_path, "rb") as f:
            pdf_data = f.read()
        base64_data = base64.b64encode(pdf_data).decode("utf-8")
        return {"base64": base64_data}
    except Exception as e:
        logger.error(f"读取PDF失败: {e}")
        raise HTTPException(status_code=500, detail="读取PDF文件失败")

@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    format: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """下载文档PDF文件（带权限检查）"""
    raw_token = token
    if not raw_token and authorization and authorization.startswith("Bearer "):
        raw_token = authorization.removeprefix("Bearer ").strip()

    if not raw_token:
        raise HTTPException(status_code=401, detail="无法验证凭据")

    current_user = await get_user_by_token(raw_token, db)
    doc = await _get_user_document(db, document_id, current_user.id)

    # 获取PDF文件路径
    pdf_path = doc.pdf_path or doc.file_path
    if not pdf_path or not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF文件不存在")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"{doc.title}.pdf"
    )

@router.post("/{document_id}/vectorize")
async def vectorize_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    对文档进行分块并向量化存储（后台任务）

    流程：
    1. 对 Markdown 文档分块
    2. 调用在线 Embedding API 生成向量
    3. 写入在线 Milvus / Zilliz 向量数据库
    """
    doc = await _get_user_document(db, document_id, current_user.id)

    markdown_content = doc.markdown_content
    if not markdown_content:
        raise HTTPException(status_code=400, detail="文档未解析，无法分块")

    # 更新状态为处理中
    doc.vectorize_status = "processing"
    doc.chunked = False
    doc.chunk_count = 0
    doc.error_message = None
    await db.commit()

    task_id = f"vectorize_{document_id}"
    await task_manager.submit_task(task_id, _execute_vectorize_task, document_id, markdown_content)
    return {"message": "向量化任务已启动", "taskId": task_id}

@router.get("/{document_id}/vectorize/status")
async def get_vectorize_status(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取向量化任务状态"""
    doc = await _get_user_document(db, document_id, current_user.id)
    chunked = _is_document_chunked(doc)

    return {
        "documentId": doc.id,
        "status": _normalize_vectorize_status(doc.vectorize_status, chunked),
        "chunked": chunked,
        "chunkCount": doc.chunk_count or 0,
        "errorMessage": doc.error_message,
    }

@router.post("/{document_id}/chunk")
async def get_document_chunks(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文档的分块结果"""
    doc = await _get_user_document(db, document_id, current_user.id)

    try:
        return await _get_document_chunks_payload(doc, db)
    except Exception as e:
        logger.error(f"获取分块失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{document_id}/chunks")
async def get_document_chunks_v2(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """以 GET 方式获取文档的分块结果"""
    doc = await _get_user_document(db, document_id, current_user.id)

    try:
        return await _get_document_chunks_payload(doc, db)
    except Exception as e:
        logger.error(f"获取分块失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/folders/{folder_id}/batch-vectorize")
async def batch_vectorize_folder(
    folder_id: str,
    mode: dict = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量向量化知识库中的所有文档

    对指定知识库下的所有文档进行分块和向量化处理
    """
    mode_name = (mode or {}).get("mode", "incremental")
    if mode_name not in {"incremental", "full"}:
        raise HTTPException(status_code=400, detail="不支持的批量向量化模式")

    # 获取该文件夹下的所有文档
    query = select(Document).where(Document.folder_id == folder_id, Document.user_id == current_user.id)
    result = await db.execute(query)
    documents = result.scalars().all()

    if not documents:
        raise HTTPException(status_code=404, detail="文件夹不存在或为空")

    vectorizable_docs = [doc for doc in documents if doc.markdown_content]
    already_vectorized = sum(1 for doc in vectorizable_docs if _is_document_chunked(doc))

    if mode_name == "full":
        pending_docs = [
            doc for doc in vectorizable_docs
            if not _is_task_active(f"vectorize_{doc.id}")
        ]
    else:
        pending_docs = [
            doc for doc in vectorizable_docs
            if not _is_document_chunked(doc)
            and not _is_task_active(f"vectorize_{doc.id}")
        ]

    task_ids = []
    scheduled_items = []
    for doc_item in pending_docs:
        doc_item.vectorize_status = "queued"
        doc_item.chunked = False
        doc_item.chunk_count = 0
        doc_item.error_message = None
        task_ids.append(f"vectorize_{doc_item.id}")
        scheduled_items.append((doc_item.id, doc_item.markdown_content))

    await db.commit()

    batch_task_id = f"batch_vectorize_{folder_id}_{int(datetime.now().timestamp())}"
    if scheduled_items:
        await task_manager.submit_task(batch_task_id, _execute_batch_vectorize_task, scheduled_items)

    return {
        "taskId": batch_task_id,
        "folderId": folder_id,
        "totalCount": len(documents),
        "alreadyVectorized": already_vectorized,
        "pendingVectorization": len(pending_docs),
        "message": f"批量向量化任务已启动，共 {len(pending_docs)} 个文档",
    }


@router.post("/folders/{folder_id}/batch-parse")
async def batch_parse_folder(
    folder_id: str,
    mode: dict = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批量解析知识库中的文档"""
    mode_name = (mode or {}).get("mode", "incremental")
    if mode_name not in {"incremental", "full", "failed"}:
        raise HTTPException(status_code=400, detail="不支持的批量解析模式")

    query = select(Document).where(Document.folder_id == folder_id, Document.user_id == current_user.id)
    result = await db.execute(query)
    documents = result.scalars().all()

    if not documents:
        raise HTTPException(status_code=404, detail="文件夹不存在或为空")

    already_parsed = sum(1 for doc in documents if doc.parsed and (doc.parse_status or "") == "success")

    if mode_name == "full":
        pending_docs = [doc for doc in documents if not _is_task_active(f"parse_{doc.id}")]
    elif mode_name == "failed":
        pending_docs = [
            doc for doc in documents
            if (doc.parse_status or "") == "error" and not _is_task_active(f"parse_{doc.id}")
        ]
    else:
        pending_docs = [
            doc for doc in documents
            if ((not doc.parsed) and (doc.parse_status or "") != "parsing")
            or (doc.parse_status or "") == "error"
        ]
        pending_docs = [doc for doc in pending_docs if not _is_task_active(f"parse_{doc.id}")]

    task_ids = []
    scheduled_items = []
    for doc_item in pending_docs:
        doc_item.parse_status = "queued"
        doc_item.parsed = False
        doc_item.chunked = False
        doc_item.vectorize_status = "pending"
        doc_item.chunk_count = 0
        doc_item.error_message = None
        task_ids.append(f"parse_{doc_item.id}")
        scheduled_items.append((doc_item.id, doc_item.pdf_path or doc_item.file_path))

    await db.commit()

    batch_task_id = f"batch_parse_{folder_id}_{int(datetime.now().timestamp())}"
    if scheduled_items:
        await task_manager.submit_task(batch_task_id, _execute_batch_parse_task, scheduled_items)

    return {
        "taskId": batch_task_id,
        "folderId": folder_id,
        "totalCount": len(documents),
        "alreadyParsed": already_parsed,
        "pendingParse": len(pending_docs),
        "message": f"批量解析任务已启动，共 {len(pending_docs)} 个文档",
    }
