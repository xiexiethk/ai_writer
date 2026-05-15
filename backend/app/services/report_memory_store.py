"""
报告写作会话的本地向量记忆存储。
"""
from __future__ import annotations

import json
import logging
import asyncio
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np

from app.services.embedding import embedding_service

logger = logging.getLogger(__name__)


class ReportMemoryStore:
    """基于本地 JSON 的报告会话记忆向量检索。"""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.storage_dir = storage_dir or (
            Path(__file__).resolve().parents[2] / "data" / "report_memory_local"
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _project_path(self, project_id: str) -> Path:
        return self.storage_dir / f"{project_id}.json"

    def _load_records(self, project_id: str) -> List[Dict[str, Any]]:
        path = self._project_path(project_id)
        if not path.exists():
            return []

        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)

        return payload if isinstance(payload, list) else []

    def _save_records(self, project_id: str, records: List[Dict[str, Any]]) -> None:
        path = self._project_path(project_id)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        left_vec = np.array(left, dtype=np.float32)
        right_vec = np.array(right, dtype=np.float32)
        denominator = float(np.linalg.norm(left_vec) * np.linalg.norm(right_vec))
        if denominator == 0:
            return 0.0
        return float(np.dot(left_vec, right_vec) / denominator)

    @staticmethod
    def _truncate(text: str, limit: int = 800) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 3] + "..."

    def upsert_memory(
        self,
        project_id: str,
        memory: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """写入或更新一条记忆记录。embedding 失败时直接跳过。"""
        content = (memory.get("content") or "").strip()
        memory_id = memory.get("memory_id") or memory.get("id")
        if not content or not memory_id:
            return None

        try:
            embedding = embedding_service.encode_single(content)
        except Exception as exc:
            logger.warning("报告会话记忆向量化失败，跳过写入: %s", exc)
            return None

        records = self._load_records(project_id)
        entry = dict(memory)
        entry["memory_id"] = memory_id
        entry["content"] = content
        entry["embedding"] = embedding

        replaced = False
        for index, record in enumerate(records):
            if record.get("memory_id") == memory_id:
                records[index] = entry
                replaced = True
                break

        if not replaced:
            records.append(entry)

        self._save_records(project_id, records)
        return entry

    def store_messages(
        self,
        project_id: str,
        conversation_id: str,
        scope_type: str,
        scope_id: str,
        messages: Iterable[Dict[str, Any]],
        user_id: Optional[int] = None,
        memory_type: str = "turn",
    ) -> None:
        """批量写入会话消息。"""
        for message in messages:
            message_id = message.get("id")
            if not message_id:
                continue

            self.upsert_memory(
                project_id,
                {
                    "memory_id": message_id,
                    "project_id": project_id,
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "message_id": message_id,
                    "role": message.get("role"),
                    "content": message.get("content", ""),
                    "memory_type": memory_type,
                    "timestamp": message.get("timestamp"),
                },
            )

    def store_summary(
        self,
        project_id: str,
        conversation_id: str,
        scope_type: str,
        scope_id: str,
        summary: str,
        summary_version: int,
        user_id: Optional[int] = None,
    ) -> None:
        """写入滚动摘要记忆。"""
        if not summary.strip():
            return

        self.upsert_memory(
            project_id,
            {
                "memory_id": f"{conversation_id}:summary:{summary_version}",
                "project_id": project_id,
                "user_id": user_id,
                "conversation_id": conversation_id,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "message_id": None,
                "role": "system",
                "content": summary,
                "memory_type": "summary",
                "timestamp": None,
            },
        )

    def search(
        self,
        project_id: str,
        query: str,
        *,
        conversation_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        top_k: int = 3,
        exclude_message_ids: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        """按需检索相关记忆。"""
        if not query.strip():
            return []

        records = self._load_records(project_id)
        if not records:
            return []

        try:
            query_embedding = embedding_service.encode_single(query)
        except Exception as exc:
            logger.warning("报告会话记忆检索向量化失败，跳过召回: %s", exc)
            return []

        excluded = set(exclude_message_ids or [])
        ranked: List[Dict[str, Any]] = []
        for record in records:
            embedding = record.get("embedding")
            if not embedding:
                continue

            message_id = record.get("message_id")
            if message_id and message_id in excluded:
                continue

            score = self._cosine_similarity(query_embedding, embedding)
            if conversation_id and record.get("conversation_id") == conversation_id:
                score += 0.04
            if scope_type and record.get("scope_type") == scope_type:
                score += 0.03
            if scope_id and record.get("scope_id") == scope_id:
                score += 0.05

            ranked.append(
                {
                    "memory_id": record.get("memory_id"),
                    "conversation_id": record.get("conversation_id"),
                    "scope_type": record.get("scope_type"),
                    "scope_id": record.get("scope_id"),
                    "role": record.get("role"),
                    "memory_type": record.get("memory_type"),
                    "content": self._truncate(record.get("content", ""), 900),
                    "score": score,
                    "timestamp": record.get("timestamp"),
                }
            )

        ranked.sort(key=lambda item: item.get("score", 0.0), reverse=True)
        unique_contents: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for item in ranked:
            content = item.get("content", "")
            if not content or content in unique_contents:
                continue
            unique_contents.add(content)
            deduped.append(item)
            if len(deduped) >= top_k:
                break
        return deduped

    async def search_async(
        self,
        project_id: str,
        query: str,
        *,
        conversation_id: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        top_k: int = 3,
        exclude_message_ids: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(
            self.search,
            project_id,
            query,
            conversation_id=conversation_id,
            scope_type=scope_type,
            scope_id=scope_id,
            top_k=top_k,
            exclude_message_ids=exclude_message_ids,
        )

    async def store_messages_async(
        self,
        project_id: str,
        conversation_id: str,
        scope_type: str,
        scope_id: str,
        messages: Iterable[Dict[str, Any]],
        user_id: Optional[int] = None,
        memory_type: str = "turn",
    ) -> None:
        await asyncio.to_thread(
            self.store_messages,
            project_id,
            conversation_id,
            scope_type,
            scope_id,
            messages,
            user_id,
            memory_type,
        )

    async def store_summary_async(
        self,
        project_id: str,
        conversation_id: str,
        scope_type: str,
        scope_id: str,
        summary: str,
        summary_version: int,
        user_id: Optional[int] = None,
    ) -> None:
        await asyncio.to_thread(
            self.store_summary,
            project_id,
            conversation_id,
            scope_type,
            scope_id,
            summary,
            summary_version,
            user_id,
        )


report_memory_store = ReportMemoryStore()
