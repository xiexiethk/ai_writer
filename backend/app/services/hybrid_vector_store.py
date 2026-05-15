"""
混合检索向量数据库服务 - 支持多用户数据隔离
使用 Milvus v2.6+ 的 MilvusClient API 支持 BM25 和向量相似度混合检索
"""
import logging
from typing import List, Dict, Optional
from app.core.config import settings
from pymilvus import (
    MilvusClient,
    DataType,
    Function,
    FunctionType,
    AnnSearchRequest,
    RRFRanker,
    WeightedRanker,
)

logger = logging.getLogger(__name__)


class HybridVectorStore:
    """混合检索向量存储服务 - 使用 MilvusClient (v2.6+)"""

    def __init__(
        self,
        uri: str = settings.MILVUS_URI,
        user: str = settings.MILVUS_USER,
        password: str = settings.MILVUS_PASSWORD,
        collection_name: str = "hybrid_document_chunks_v2"  # 升级版本以包含 user_id
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.collection_name = collection_name
        self.client = None
        self.connected = False

    @staticmethod
    def _format_string_list_for_expr(values: List[str]) -> str:
        """格式化字符串列表为 Milvus 过滤表达式可用的数组字面量"""
        escaped_values = []
        for value in values:
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            escaped_values.append(f'"{escaped}"')
        return "[" + ", ".join(escaped_values) + "]"

    def connect(self):
        """连接到 Milvus"""
        try:
            self.client = MilvusClient(
                uri=self.uri,
                user=self.user or "",
                password=self.password or "",
            )
            self.connected = True
            logger.info(f"成功连接到 Milvus: {self.uri}")
        except Exception as e:
            logger.error(f"连接 Milvus 失败: {e}")
            raise

    def create_collection(
        self,
        dimension: int,
        drop_existing: bool = False
    ):
        if not self.connected:
            self.connect()

        if self.client.has_collection(self.collection_name):
            if drop_existing:
                self.client.drop_collection(self.collection_name)
            else:
                return

        analyzer_params = {"tokenizer": "standard", "filter": ["lowercase"]}
        schema = MilvusClient.create_schema()
        
        schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=256)
        schema.add_field(field_name="document_id", datatype=DataType.VARCHAR, max_length=256)
        schema.add_field(field_name="user_id", datatype=DataType.INT64) # 新增 user_id 字段
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
        schema.add_field(field_name="level", datatype=DataType.INT64)
        schema.add_field(
            field_name="content",
            datatype=DataType.VARCHAR,
            max_length=65535,
            analyzer_params=analyzer_params,
            enable_match=True,
            enable_analyzer=True,
        )
        schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=dimension)

        bm25_function = Function(
            name="bm25",
            function_type=FunctionType.BM25,
            input_field_names=["content"],
            output_field_names="sparse_vector",
        )
        schema.add_function(bm25_function)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(field_name="sparse_vector", index_type="SPARSE_INVERTED_INDEX", metric_type="BM25")
        index_params.add_index(field_name="dense_vector", index_type="FLAT", metric_type="COSINE")

        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )

    def insert_chunks(
        self,
        chunks: List[Dict],
        embeddings: List[List[float]],
        user_id: int # 强制要求传入 user_id
    ):
        if not self.connected:
            self.connect()

        entities = []
        for i, chunk in enumerate(chunks):
            entity = {
                "id": chunk["id"],
                "document_id": chunk["document_id"],
                "user_id": user_id,
                "chunk_index": chunk["chunk_index"],
                "title": chunk.get("title", ""),
                "content": chunk["content"],
                "level": chunk.get("level", 0),
                "dense_vector": embeddings[i],
            }
            entities.append(entity)

        self.client.insert(collection_name=self.collection_name, data=entities)

    def hybrid_search(
        self,
        query_text: str,
        query_vector: List[float],
        user_id: int, # 强制要求过滤 user_id
        top_k: int = 10,
        document_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        sparse_weight: float = 0.5,
        dense_weight: float = 0.5,
        use_rrf: bool = True
    ) -> List[Dict]:
        if not self.connected:
            self.connect()

        # 强制实施用户隔离过滤
        expr = f"user_id == {user_id}"
        if document_ids is not None:
            if not document_ids:
                return []
            if len(document_ids) == 1:
                expr += f" and document_id == '{document_ids[0]}'"
            else:
                expr += f" and document_id in {self._format_string_list_for_expr(document_ids)}"
        elif document_id:
            expr += f" and document_id == '{document_id}'"

        sparse_request = AnnSearchRequest(data=[query_text], anns_field="sparse_vector", param={"metric_type": "BM25"}, limit=top_k, expr=expr)
        dense_request = AnnSearchRequest(data=[query_vector], anns_field="dense_vector", param={"metric_type": "COSINE"}, limit=top_k, expr=expr)

        ranker = RRFRanker() if use_rrf else WeightedRanker(sparse_weight, dense_weight)

        results = self.client.hybrid_search(
            collection_name=self.collection_name,
            reqs=[sparse_request, dense_request],
            ranker=ranker,
            limit=top_k,
            output_fields=["document_id", "chunk_index", "title", "content", "level"]
        )

        formatted_results = []
        if results and len(results) > 0:
            for hit in results[0]:
                formatted_results.append({
                    "id": hit["id"],
                    "score": hit["distance"],
                    "document_id": hit["entity"].get("document_id"),
                    "chunk_index": hit["entity"].get("chunk_index"),
                    "title": hit["entity"].get("title", ""),
                    "content": hit["entity"].get("content", ""),
                    "level": hit["entity"].get("level", 0)
                })
        return formatted_results

    def delete_document(self, document_id: str):
        if not self.connected:
            self.connect()
        try:
            self.client.load_collection(collection_name=self.collection_name)
        except Exception:
            pass

        try:
            self.client.delete(collection_name=self.collection_name, filter=f"document_id == '{document_id}'")
        except Exception as e:
            logger.warning(f"删除混合集合中的文档 {document_id} 失败，继续后续写入: {e}")


# 全局混合检索向量存储实例
hybrid_vector_store = HybridVectorStore()
