"""
文本向量化服务。
使用 OpenAI text-embedding-3-small API。
"""
from __future__ import annotations

import logging
import time
from typing import List, Union, Optional

import numpy as np

from app.services.llm_gateway import (
    embedding_request,
    embedding_request_async,
    embedding_model_note,
    get_endpoint_status,
    resolve_embedding_base_url,
    resolve_embedding_model,
    resolve_embedding_provider,
)

logger = logging.getLogger(__name__)


class EmbeddingService:
    """文本嵌入服务，使用 OpenAI text-embedding-3-small。"""

    def __init__(
        self,
        model_name: Optional[str] = None,
        provider: Optional[str] = None,
    ):
        self.provider = resolve_embedding_provider(provider)
        self.model_name = resolve_embedding_model(self.provider, model_name)
        self.dimension = 1536  # text-embedding-3-small 固定 1536 维
        self.batch_size = 32
        self.max_retries = 2

        note = embedding_model_note(self.model_name)
        if note:
            logger.info(note)

        self._initialize_dimension()

    def _initialize_dimension(self):
        """初始化时检测正确的向量维度。"""
        try:
            embeddings = embedding_request(
                "初始化",
                provider=self.provider,
                model=self.model_name,
                timeout=30.0,
            )
            if embeddings and embeddings[0]:
                self.dimension = len(embeddings[0])
                logger.info(f"Embedding 服务初始化完成，向量维度: {self.dimension}")
        except Exception as e:
            logger.warning(f"无法自动检测向量维度，使用默认值 1536: {e}")

    def _request_embeddings_with_retry(
        self,
        texts: Union[str, List[str]],
        *,
        timeout: float,
    ) -> List[List[float]]:
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                return embedding_request(
                    texts,
                    provider=self.provider,
                    model=self.model_name,
                    timeout=timeout,
                )
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break

                delay = min(2.0, 0.5 * (2 ** attempt))
                logger.warning(
                    "Embedding 请求失败，%.1f 秒后重试（%s/%s）: %s",
                    delay,
                    attempt + 1,
                    self.max_retries,
                    exc,
                )
                time.sleep(delay)

        assert last_error is not None
        raise last_error

    def _append_embedding(
        self,
        raw_embedding: List[float],
        text_index: int,
        embeddings: List[np.ndarray],
        successful_indices: List[int],
        expected_dim: Optional[int],
    ) -> Optional[int]:
        if not raw_embedding:
            logger.warning(f"第 {text_index} 个文本的向量为空，跳过")
            return expected_dim

        embedding = np.array(raw_embedding, dtype=np.float32)
        if len(embedding) == 0:
            logger.warning(f"第 {text_index} 个文本的向量为空，跳过")
            return expected_dim

        if expected_dim is None:
            expected_dim = len(embedding)
            self.dimension = expected_dim
            logger.info(f"设置向量维度为: {expected_dim}")

        if len(embedding) != expected_dim:
            logger.warning(
                f"第 {text_index} 个文本的向量维度 ({len(embedding)}) 与期望维度 ({expected_dim}) 不一致，跳过"
            )
            return expected_dim

        embeddings.append(embedding)
        successful_indices.append(text_index)
        return expected_dim

    def _encode_texts(self, texts: List[str]) -> tuple[List[int], List[np.ndarray]]:
        embeddings: List[np.ndarray] = []
        successful_indices: List[int] = []
        expected_dim = None

        for batch_start in range(0, len(texts), self.batch_size):
            batch_texts = texts[batch_start:batch_start + self.batch_size]
            batch_end = batch_start + len(batch_texts) - 1

            try:
                batch_result = self._request_embeddings_with_retry(batch_texts, timeout=120.0)
                if len(batch_result) != len(batch_texts):
                    raise ValueError(
                        f"批量请求返回向量数量不匹配: {len(batch_result)} != {len(batch_texts)}"
                    )

                for offset, raw_embedding in enumerate(batch_result):
                    expected_dim = self._append_embedding(
                        raw_embedding,
                        batch_start + offset,
                        embeddings,
                        successful_indices,
                        expected_dim,
                    )
            except Exception as exc:
                logger.warning(
                    "批量编码第 %s-%s 个文本失败: %s，回退到逐条请求",
                    batch_start,
                    batch_end,
                    exc,
                )
                for offset, text in enumerate(batch_texts):
                    text_index = batch_start + offset
                    try:
                        single_result = self._request_embeddings_with_retry(text, timeout=60.0)
                        expected_dim = self._append_embedding(
                            single_result[0] if single_result else [],
                            text_index,
                            embeddings,
                            successful_indices,
                            expected_dim,
                        )
                    except Exception as single_exc:
                        logger.warning(f"编码第 {text_index} 个文本失败: {single_exc}，跳过")
                        continue

        return successful_indices, embeddings

    async def encode_async(self, texts: Union[str, List[str]]) -> np.ndarray:
        """异步将文本编码为向量。"""
        if isinstance(texts, str):
            texts = [texts]

        try:
            embeddings = await embedding_request_async(
                texts,
                provider=self.provider,
                model=self.model_name,
                timeout=300.0,
            )
            vectors = [np.array(embedding, dtype=np.float32) for embedding in embeddings if embedding]

            if not vectors:
                raise ValueError("没有成功编码任何文本")

            if self.dimension != len(vectors[0]):
                self.dimension = len(vectors[0])
                logger.info(f"更新向量维度为: {self.dimension}")

            logger.info(f"成功编码 {len(vectors)} 个文本")
            return np.array(vectors)
        except Exception as e:
            logger.error(f"文本编码失败: {e}")
            raise

    def encode(self, texts: Union[str, List[str]]) -> np.ndarray:
        """将文本编码为向量（同步版本）。"""
        if isinstance(texts, str):
            texts = [texts]

        try:
            _, embeddings = self._encode_texts(texts)

            if not embeddings:
                raise ValueError("没有成功编码任何文本")

            logger.info(f"成功编码 {len(embeddings)} 个文本，向量维度: {len(embeddings[0])}")
            return np.array(embeddings)
        except Exception as e:
            logger.error(f"文本编码失败: {e}")
            raise

    def encode_with_indices(self, texts: List[str]) -> tuple[List[int], np.ndarray]:
        """编码文本并返回成功的索引和向量。"""
        try:
            successful_indices, embeddings = self._encode_texts(texts)

            if not embeddings:
                raise ValueError("没有成功编码任何文本")

            logger.info(
                f"成功编码 {len(embeddings)} 个文本（共 {len(texts)} 个），向量维度: {len(embeddings[0])}"
            )
            return successful_indices, np.array(embeddings)
        except Exception as e:
            logger.error(f"文本编码失败: {e}")
            raise

    def encode_single(self, text: str) -> List[float]:
        """编码单个文本，返回列表格式。"""
        embedding = self.encode(text)
        return embedding[0].tolist()

    def unload_model(self):
        """卸载模型 - OpenAI API 无本地模型，直接返回成功。"""
        logger.info("OpenAI API 模式，无需卸载模型")
        return True

    def warmup(self):
        """预热模型 - OpenAI API 模式，发送一次请求验证连接。"""
        try:
            embedding = self.encode_single("预热模型")
            if embedding:
                self.dimension = len(embedding)
                logger.info(f"模型预热完成，向量维度: {self.dimension}")
            return True
        except Exception as e:
            logger.error(f"模型预热失败: {e}")
            return False

    def test_connection(self) -> bool:
        """测试当前 embedding 提供方连接。"""
        try:
            status = get_endpoint_status(
                provider=self.provider,
                base_url=resolve_embedding_base_url(self.provider),
                model_name=self.model_name,
            )
            model_names = status.get("available_models", [])
            if self.model_name in model_names:
                logger.info("%s 连接成功，模型 %s 可用", self.provider, self.model_name)
                return True
            logger.warning(f"模型 {self.model_name} 不在可用模型列表中: {model_names}")
            return False
        except Exception as e:
            logger.error(f"{self.provider} 连接失败: {e}")
            return False


# 全局嵌入服务实例
embedding_service = EmbeddingService()
