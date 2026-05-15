"""
高级轻量检索编排器。

目标：在不进入重型 Agent 循环的前提下，基于问题形态选择轻量策略
（direct / rewrite / multi_query / step_back），并行检索后统一合并排序。
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.services.agent_engine.llm import create_chat_llm
from app.services.agent_engine.prompts import (
    MULTI_QUERY_GENERATION_PROMPT,
    REWRITE_GENERATION_PROMPT,
    STEP_BACK_GENERATION_PROMPT,
)
from app.services.retrieval_helper import search_with_variants

logger = logging.getLogger(__name__)

RetrievalSearchFn = Callable[[str, int, Optional[List[str]]], List[Dict]]

MAX_QUERY_VARIANTS = 3
MAX_HISTORY_MESSAGES = 6


@dataclass
class RetrievalResult:
    selected_strategy: str
    queries: List[str]
    chunks: List[Dict]
    debug: Dict


class RetrievalOrchestrator:
    def __init__(
        self,
        provider: str = "deepseek",
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.2,
    ):
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            self._llm = create_chat_llm(
                provider=self.provider,
                model=self.model,
                base_url=self.base_url,
                temperature=self.temperature,
            )
        return self._llm

    @staticmethod
    def _normalize_history(conversation_history: Optional[List[Dict]]) -> List[Dict]:
        if not conversation_history:
            return []
        normalized: List[Dict] = []
        for item in conversation_history[-MAX_HISTORY_MESSAGES:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                normalized.append({"role": role, "content": content})
        return normalized

    @staticmethod
    def _has_context_dependency(query: str, conversation_history: Optional[List[Dict]]) -> bool:
        text = (query or "").strip()
        if not text:
            return False
        if conversation_history:
            pronouns = ("它", "这个", "那个", "那", "前文", "上文", "继续", "上一个", "前者", "后者")
            return any(token in text for token in pronouns)
        return False

    @staticmethod
    def _should_use_multi_query(query: str, mode: str) -> bool:
        text = (query or "").strip()
        if mode in {"outline", "section", "report_edit"}:
            if any(token in text for token in ("综述", "总结", "大纲", "章节", "框架", "主题", "核心内容")):
                return True
        clause_markers = ("、", "；", "分别", "对比", "比较", "差异", "异同")
        if any(marker in text for marker in clause_markers):
            return True
        return len(text) >= 18 and sum(text.count(sep) for sep in ("，", "；", "。")) >= 2

    @staticmethod
    def _should_use_step_back(query: str, mode: str) -> bool:
        text = (query or "").strip()
        if mode in {"outline", "section"}:
            return any(token in text for token in ("综述", "主题", "背景", "发展", "原理", "框架", "核心内容"))
        return len(text) >= 18 and any(token in text for token in ("原理", "背景", "演变", "机制", "体系", "框架", "影响", "原因"))

    def select_strategy(
        self,
        *,
        query: str,
        mode: str,
        conversation_history: Optional[List[Dict]],
        document_ids: Optional[List[str]],
    ) -> str:
        if not (document_ids or []):
            return "direct"
        if self._has_context_dependency(query, conversation_history):
            return "rewrite"
        if self._should_use_multi_query(query, mode):
            return "multi_query"
        if self._should_use_step_back(query, mode):
            return "step_back"
        return "direct"

    async def _rewrite_query(self, query: str, conversation_history: Optional[List[Dict]]) -> str:
        history = self._normalize_history(conversation_history)
        history_str = "\n".join(f"[{item['role']}: {item['content']}]" for item in history)
        chain = ChatPromptTemplate.from_template(REWRITE_GENERATION_PROMPT) | self._get_llm() | StrOutputParser()
        rewritten = (await chain.ainvoke({"question": query, "chat_history": history_str})).strip()
        return rewritten or query

    async def _step_back_query(self, query: str) -> str:
        chain = ChatPromptTemplate.from_template(STEP_BACK_GENERATION_PROMPT) | self._get_llm() | StrOutputParser()
        abstract = (await chain.ainvoke({"question": query})).strip()
        return abstract or query

    async def _multi_queries(self, query: str) -> List[str]:
        chain = ChatPromptTemplate.from_template(MULTI_QUERY_GENERATION_PROMPT) | self._get_llm() | StrOutputParser()
        raw = (await chain.ainvoke({"question": query})).strip()
        queries = [item.strip() for item in raw.split("\n") if item.strip()]
        return queries[: MAX_QUERY_VARIANTS - 1] if queries else []

    async def build_queries(
        self,
        *,
        query: str,
        mode: str,
        conversation_history: Optional[List[Dict]],
        document_ids: Optional[List[str]],
    ) -> tuple[str, List[str]]:
        strategy = self.select_strategy(
            query=query,
            mode=mode,
            conversation_history=conversation_history,
            document_ids=document_ids,
        )
        queries: List[str] = [query]

        try:
            if strategy == "rewrite":
                rewritten = await self._rewrite_query(query, conversation_history)
                if rewritten and rewritten != query:
                    queries = [rewritten, query]
            elif strategy == "step_back":
                abstract = await self._step_back_query(query)
                if abstract and abstract != query:
                    queries = [query, abstract]
            elif strategy == "multi_query":
                expanded = await self._multi_queries(query)
                queries = [query] + [item for item in expanded if item != query]
        except Exception as exc:
            logger.warning("轻量检索策略 %s 生成查询失败，回退 direct: %s", strategy, exc)
            strategy = "direct"
            queries = [query]

        deduped: List[str] = []
        for item in queries:
            if item and item not in deduped:
                deduped.append(item)
        return strategy, deduped[:MAX_QUERY_VARIANTS]

    async def retrieve(
        self,
        *,
        query: str,
        user_id: Optional[int],
        document_ids: Optional[List[str]],
        mode: str,
        top_k: int,
        conversation_history: Optional[List[Dict]],
        search_fn: RetrievalSearchFn,
    ) -> RetrievalResult:
        strategy, planned_queries = await self.build_queries(
            query=query,
            mode=mode,
            conversation_history=conversation_history,
            document_ids=document_ids,
        )

        async def run_one(index: int, planned_query: str):
            results = await asyncio.to_thread(
                search_with_variants,
                query=planned_query,
                top_k=max(top_k, 4),
                user_id=user_id,
                extra_queries=[query] if planned_query != query else None,
                search_fn=lambda sq: search_fn(sq, max(top_k, 4), document_ids),
            )
            return index, planned_query, results

        gathered = await asyncio.gather(*(run_one(i, q) for i, q in enumerate(planned_queries)))

        merged: Dict[str, Dict] = {}
        for index, planned_query, results in gathered:
            query_bonus = max(0.0, 0.02 * (len(planned_queries) - index - 1))
            for rank, item in enumerate(results):
                item_id = item.get("id")
                if not item_id:
                    continue
                candidate = dict(item)
                candidate["score"] = float(candidate.get("score", 0.0)) + query_bonus + max(0.0, 0.01 * (3 - rank))
                existing = merged.get(item_id)
                if existing is None or candidate["score"] > float(existing.get("score", 0.0)):
                    merged[item_id] = candidate

        final_chunks = sorted(merged.values(), key=lambda item: float(item.get("score", 0.0)), reverse=True)[:top_k]
        debug = {
            "strategy": strategy,
            "query_count": len(planned_queries),
            "planned_queries": planned_queries,
            "result_count": len(final_chunks),
            "history_used": bool(conversation_history),
        }
        return RetrievalResult(strategy, planned_queries, final_chunks, debug)


retrieval_orchestrator = RetrievalOrchestrator()
