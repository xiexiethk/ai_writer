"""
在线向量数据库服务。
仅使用 Milvus / Zilliz Cloud，不再回退到本地文件。
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from pymilvus import DataType, MilvusClient

from app.core.config import settings

logger = logging.getLogger(__name__)


class VectorStore:
    """Milvus 向量存储服务。"""

    def __init__(
        self,
        *,
        uri: str = settings.MILVUS_URI,
        user: str = settings.MILVUS_USER,
        password: str = settings.MILVUS_PASSWORD,
        collection_name: str = "document_chunks_v2",
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.collection_name = collection_name
        self.client: Optional[MilvusClient] = None
        self.connected = False

    def connect(self):
        """连接到在线 Milvus / Zilliz。"""
        if self.connected and self.client is not None:
            return

        if not self.uri:
            raise RuntimeError("未配置 MILVUS_URI，无法连接在线向量数据库")

        try:
            self.client = MilvusClient(
                uri=self.uri,
                user=self.user or "",
                password=self.password or "",
            )
            self.connected = True
            logger.info("成功连接到 Milvus: %s", self.uri)
        except Exception as exc:
            self.client = None
            self.connected = False
            raise RuntimeError(f"连接在线向量数据库失败: {exc}") from exc

    def create_collection(self, dimension: int, drop_existing: bool = False):
        """创建向量集合。"""
        self.connect()
        assert self.client is not None

        if self.client.has_collection(self.collection_name):
            if drop_existing:
                self.client.drop_collection(self.collection_name)
            else:
                return

        schema = MilvusClient.create_schema()
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="level", datatype=DataType.INT64)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dimension)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="IVF_FLAT", metric_type="COSINE", params={"nlist": 128})

        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )
        logger.info("创建新集合: %s, 维度: %s", self.collection_name, dimension)

    def insert_chunks(
        self,
        chunks: List[Dict],
        embeddings: List[List[float]],
    ):
        """插入文档块。"""
        self.connect()
        assert self.client is not None

        if len(chunks) != len(embeddings):
            raise ValueError(f"分块数量与向量数量不一致: {len(chunks)} != {len(embeddings)}")

        entities = []
        for chunk, embedding in zip(chunks, embeddings):
            entities.append(
                {
                    "id": chunk["id"],
                    "document_id": chunk["document_id"],
                    "chunk_index": chunk["chunk_index"],
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "level": chunk["level"],
                    "vector": embedding,
                }
            )

        self.client.insert(collection_name=self.collection_name, data=entities)
        logger.info("成功插入 %s 个文档块", len(entities))

    def get_chunks_by_document(self, document_id: str) -> List[Dict]:
        """根据文档 ID 获取所有分块。"""
        self.connect()
        assert self.client is not None

        if not self.client.has_collection(self.collection_name):
            return []

        self.client.load_collection(collection_name=self.collection_name)
        results = self.client.query(
            collection_name=self.collection_name,
            filter=f'document_id == "{document_id}"',
            output_fields=["id", "document_id", "chunk_index", "title", "content", "level"],
        )
        results.sort(key=lambda item: item.get("chunk_index", 0))
        return results

    def search(
        self,
        query_vector: List[float],
        top_k: int = 10,
        document_id: Optional[str] = None,
    ) -> List[Dict]:
        """向量搜索。"""
        self.connect()
        assert self.client is not None

        if not self.client.has_collection(self.collection_name):
            return []

        self.client.load_collection(collection_name=self.collection_name)
        filter_expr = f'document_id == "{document_id}"' if document_id else ""
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            limit=top_k,
            filter=filter_expr,
            anns_field="vector",
            search_params={"metric_type": "COSINE", "params": {"nprobe": 10}},
            output_fields=["document_id", "chunk_index", "title", "content", "level"],
        )

        formatted_results: List[Dict] = []
        for hit in results[0]:
            entity = hit.get("entity", {})
            formatted_results.append(
                {
                    "id": hit.get("id"),
                    "score": hit.get("distance", 0.0),
                    "document_id": entity.get("document_id"),
                    "chunk_index": entity.get("chunk_index"),
                    "title": entity.get("title"),
                    "content": entity.get("content"),
                    "level": entity.get("level"),
                }
            )

        logger.info("搜索完成，返回 %s 个结果", len(formatted_results))
        return formatted_results

    def get_document_chunks(self, document_id: str) -> List[Dict]:
        """获取文档块。"""
        return self.get_chunks_by_document(document_id)

    def delete_document(self, document_id: str):
        """删除文档已有向量块。"""
        self.connect()
        assert self.client is not None

        if not self.client.has_collection(self.collection_name):
            return

        self.client.load_collection(collection_name=self.collection_name)
        self.client.delete(
            collection_name=self.collection_name,
            filter=f'document_id == "{document_id}"',
        )
        logger.info("删除文档 %s 的所有块", document_id)


vector_store = VectorStore()
