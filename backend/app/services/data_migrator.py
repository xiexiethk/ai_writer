"""
数据迁移工具
从旧 Milvus 集合迁移数据到新 Milvus 混合检索集合
"""
import logging
from typing import List, Dict, Optional
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from tqdm import tqdm

from app.core.config import settings
from app.models.document_db import Document
from app.services.vector_store import vector_store
from app.services.hybrid_vector_store import hybrid_vector_store
from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)


class DataMigrator:
    """数据迁移工具类"""

    def __init__(
        self,
        old_collection_name: Optional[str] = None,
        new_collection_name: Optional[str] = None,
        batch_size: int = 100
    ):
        """
        初始化数据迁移工具

        Args:
            old_collection_name: 旧集合名称
            new_collection_name: 新集合名称
            batch_size: 批量插入大小
        """
        self.old_collection_name = old_collection_name or vector_store.collection_name
        self.new_collection_name = new_collection_name or hybrid_vector_store.collection_name
        self.batch_size = batch_size
        self._document_user_cache: Dict[str, int] = {}

    def _build_source_store(self):
        """构建旧集合访问器。"""
        return vector_store.__class__(
            host=vector_store.host,
            port=vector_store.port,
            collection_name=self.old_collection_name,
        )

    def _build_target_store(self):
        """构建目标混合检索集合访问器。"""
        return hybrid_vector_store.__class__(
            uri=hybrid_vector_store.uri,
            collection_name=self.new_collection_name,
        )

    @staticmethod
    def _sync_database_url() -> str:
        """将异步数据库 URL 转为同步 SQLAlchemy URL。"""
        return settings.DATABASE_URL.replace("+aiosqlite", "")

    def _get_document_user_map(self, document_ids: List[str]) -> Dict[str, int]:
        """批量获取文档所属用户。"""
        uncached_ids = [doc_id for doc_id in document_ids if doc_id not in self._document_user_cache]
        if uncached_ids:
            engine = create_engine(self._sync_database_url())
            try:
                with Session(engine) as session:
                    rows = session.execute(
                        select(Document.id, Document.user_id).where(Document.id.in_(uncached_ids))
                    ).all()
                    for document_id, user_id in rows:
                        self._document_user_cache[document_id] = user_id
            finally:
                engine.dispose()

        return {
            document_id: self._document_user_cache[document_id]
            for document_id in document_ids
            if document_id in self._document_user_cache
        }

    def _ensure_hybrid_collection(self, target_store, dimension: int):
        """按当前 embedding 维度确保新集合存在。"""
        if not target_store.connected:
            target_store.connect()

        if not target_store.client.has_collection(self.new_collection_name):
            logger.info(f"创建新集合: {self.new_collection_name}，向量维度: {dimension}")
            target_store.create_collection(
                dimension=dimension,
                drop_existing=False
            )

    def _insert_grouped_chunks(
        self,
        target_store,
        chunks: List[Dict],
        embeddings: List[List[float]],
        user_map: Dict[str, int],
    ):
        """按 user_id 分组写入目标集合。"""
        grouped_chunks: Dict[int, List[Dict]] = {}
        grouped_embeddings: Dict[int, List[List[float]]] = {}

        for chunk, embedding in zip(chunks, embeddings):
            document_id = chunk["document_id"]
            user_id = user_map.get(document_id)
            if user_id is None:
                raise ValueError(f"文档 {document_id} 缺少 user_id，无法迁移到混合检索集合")

            grouped_chunks.setdefault(user_id, []).append(chunk)
            grouped_embeddings.setdefault(user_id, []).append(embedding)

        for user_id, user_chunks in grouped_chunks.items():
            target_store.insert_chunks(
                user_chunks,
                grouped_embeddings[user_id],
                user_id=user_id,
            )

    def migrate_document(
        self,
        document_id: str,
        create_collection_if_not_exists: bool = True
    ) -> int:
        """
        迁移单个文档的所有块

        Args:
            document_id: 文档 ID
            create_collection_if_not_exists: 如果新集合不存在，是否创建

        Returns:
            迁移的块数量
        """
        try:
            source_store = self._build_source_store()
            target_store = self._build_target_store()

            # 从旧集合获取文档块
            logger.info(f"从旧集合读取文档 {document_id} 的块...")
            if not source_store.connected:
                source_store.connect()
            old_chunks = source_store.get_chunks_by_document(document_id)

            if not old_chunks:
                logger.warning(f"文档 {document_id} 在旧集合中不存在")
                return 0

            # 准备数据
            chunks = []
            texts = []
            for chunk in old_chunks:
                chunk_dict = {
                    "id": chunk.get("id", ""),
                    "document_id": chunk.get("document_id", document_id),
                    "chunk_index": chunk.get("chunk_index", 0),
                    "title": chunk.get("title", ""),
                    "content": chunk.get("content", ""),
                    "level": chunk.get("level", 0)
                }
                chunks.append(chunk_dict)
                texts.append(chunk.get("content", ""))

            if not chunks:
                logger.warning(f"文档 {document_id} 没有有效的块")
                return 0

            # 生成密集向量
            logger.info(f"生成 {len(texts)} 个文本的向量...")
            embeddings = embedding_service.encode(texts)
            embeddings_list = embeddings.tolist()
            user_map = self._get_document_user_map([document_id])

            if embeddings_list and (
                create_collection_if_not_exists
                or not target_store.client
                or not target_store.client.has_collection(self.new_collection_name)
            ):
                self._ensure_hybrid_collection(target_store, len(embeddings_list[0]))

            # 插入到新集合
            logger.info(f"插入 {len(chunks)} 个块到新集合...")
            self._insert_grouped_chunks(target_store, chunks, embeddings_list, user_map)

            logger.info(f"成功迁移文档 {document_id}，共 {len(chunks)} 个块")
            return len(chunks)

        except Exception as e:
            logger.error(f"迁移文档 {document_id} 失败: {e}")
            raise

    def migrate_all_documents(
        self,
        document_ids: Optional[List[str]] = None,
        create_collection_if_not_exists: bool = True
    ) -> Dict[str, int]:
        """
        迁移所有文档或指定文档列表

        Args:
            document_ids: 要迁移的文档ID列表，如果为 None 则迁移所有文档
            create_collection_if_not_exists: 如果新集合不存在，是否创建

        Returns:
            迁移结果统计，格式为 {document_id: 迁移的块数量}
        """
        try:
            # 如果没有指定文档ID列表，需要从旧集合获取所有文档ID
            if document_ids is None:
                logger.info("获取所有文档ID...")
                # 从旧集合查询所有唯一的 document_id
                # 注意：这里需要根据实际情况调整，因为旧 API 可能不支持直接查询所有 document_id
                # 可以通过查询所有数据然后提取唯一的 document_id
                logger.warning("未指定文档ID列表，需要手动提供或实现自动获取逻辑")
                return {}

            # 迁移每个文档
            results = {}
            total_chunks = 0

            logger.info(f"开始迁移 {len(document_ids)} 个文档...")
            for doc_id in tqdm(document_ids, desc="迁移文档"):
                try:
                    chunk_count = self.migrate_document(
                        doc_id,
                        create_collection_if_not_exists=create_collection_if_not_exists
                    )
                    results[doc_id] = chunk_count
                    total_chunks += chunk_count
                except Exception as e:
                    logger.error(f"迁移文档 {doc_id} 失败: {e}")
                    results[doc_id] = 0

            logger.info(f"迁移完成，共迁移 {total_chunks} 个块")
            return results

        except Exception as e:
            logger.error(f"批量迁移失败: {e}")
            raise

    def migrate_by_batch(
        self,
        document_ids: List[str],
        create_collection_if_not_exists: bool = True
    ) -> Dict[str, int]:
        """
        批量迁移文档（按批次处理，提高效率）

        Args:
            document_ids: 要迁移的文档ID列表
            create_collection_if_not_exists: 如果新集合不存在，是否创建

        Returns:
            迁移结果统计
        """
        try:
            source_store = self._build_source_store()
            target_store = self._build_target_store()
            if not source_store.connected:
                source_store.connect()
            if not target_store.connected:
                target_store.connect()

            # 按批次处理
            results = {}
            total_chunks = 0

            logger.info(f"开始批量迁移 {len(document_ids)} 个文档，批次大小: {self.batch_size}")

            for i in range(0, len(document_ids), self.batch_size):
                batch = document_ids[i:i + self.batch_size]
                logger.info(f"处理批次 {i // self.batch_size + 1}，包含 {len(batch)} 个文档")

                # 收集批次中的所有块
                all_chunks = []
                all_texts = []

                for doc_id in batch:
                    try:
                        old_chunks = source_store.get_chunks_by_document(doc_id)
                        for chunk in old_chunks:
                            chunk_dict = {
                                "id": chunk.get("id", ""),
                                "document_id": chunk.get("document_id", doc_id),
                                "chunk_index": chunk.get("chunk_index", 0),
                                "title": chunk.get("title", ""),
                                "content": chunk.get("content", ""),
                                "level": chunk.get("level", 0)
                            }
                            all_chunks.append(chunk_dict)
                            all_texts.append(chunk.get("content", ""))
                    except Exception as e:
                        logger.warning(f"读取文档 {doc_id} 失败: {e}")
                        continue

                if not all_chunks:
                    logger.warning(f"批次 {i // self.batch_size + 1} 没有有效数据")
                    continue

                # 批量生成向量
                logger.info(f"生成 {len(all_texts)} 个文本的向量...")
                embeddings = embedding_service.encode(all_texts)
                embeddings_list = embeddings.tolist()
                user_map = self._get_document_user_map(batch)

                if embeddings_list and (
                    create_collection_if_not_exists
                    or not target_store.client.has_collection(self.new_collection_name)
                ):
                    self._ensure_hybrid_collection(target_store, len(embeddings_list[0]))
                    create_collection_if_not_exists = False

                # 批量插入
                logger.info(f"插入 {len(all_chunks)} 个块到新集合...")
                self._insert_grouped_chunks(target_store, all_chunks, embeddings_list, user_map)

                # 记录结果
                for doc_id in batch:
                    doc_chunks = [c for c in all_chunks if c["document_id"] == doc_id]
                    results[doc_id] = len(doc_chunks)
                    total_chunks += len(doc_chunks)

            logger.info(f"批量迁移完成，共迁移 {total_chunks} 个块")
            return results

        except Exception as e:
            logger.error(f"批量迁移失败: {e}")
            raise


# 全局数据迁移工具实例
data_migrator = DataMigrator()
