"""
检索辅助工具
提供轻量查询归一化、变体生成和标题命中重排。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Dict, List, Optional


_DB_PATH = Path(__file__).resolve().parents[2] / "ai_writer.db"

_QUERY_REPLACEMENTS = (
    ("退伍军人", "退役军人"),
    ("退伍", "退役"),
    ("复员军人", "退役军人"),
)

_QUESTION_FILLERS = (
    "请问",
    "如何",
    "怎么办",
    "怎么",
    "怎样",
    "是什么",
    "有哪些",
    "有啥",
    "吗",
    "呢",
    "？",
    "?",
    "。",
    "，",
    ",",
    "、",
)

_DOMAIN_FILLERS = (
    "政策",
    "具体措施",
    "相关规定",
    "有关规定",
)

_LEGAL_SUFFIXES = ("条例", "办法", "规定", "法", "细则")
_LEGAL_HINT_TERMS = ("安置", "待遇", "优待", "保护", "管理", "保障", "抚恤", "补助", "就业")


def normalize_query_text(query: str) -> str:
    """做轻量同义词归一化，提升口语问法召回率"""
    normalized = (query or "").strip()
    for src, target in _QUERY_REPLACEMENTS:
        normalized = normalized.replace(src, target)
    return normalized


def build_query_variants(query: str) -> List[str]:
    """为单个查询生成少量高价值变体，避免依赖大模型改写"""
    variants: List[str] = []

    def add_variant(value: str):
        candidate = " ".join((value or "").split()).strip()
        if candidate and candidate not in variants:
            variants.append(candidate)

    original = (query or "").strip()
    add_variant(original)

    normalized = normalize_query_text(original)
    add_variant(normalized)

    keyword = normalized
    for filler in _QUESTION_FILLERS:
        keyword = keyword.replace(filler, " ")
    compact_keyword = "".join(keyword.split()).strip()
    add_variant(compact_keyword)

    legal_keyword = compact_keyword
    for filler in _DOMAIN_FILLERS:
        legal_keyword = legal_keyword.replace(filler, "")
    legal_keyword = legal_keyword.strip()
    add_variant(legal_keyword)

    if legal_keyword and not legal_keyword.endswith(_LEGAL_SUFFIXES):
        if any(term in legal_keyword for term in _LEGAL_HINT_TERMS):
            add_variant(legal_keyword + "条例")

    return variants


def get_document_titles(document_ids: List[str], user_id: Optional[int] = None) -> Dict[str, str]:
    """同步读取文档标题，供检索重排使用"""
    unique_ids = list(dict.fromkeys(document_ids))
    if not unique_ids or not _DB_PATH.exists():
        return {}

    placeholders = ",".join("?" for _ in unique_ids)
    sql = f"select id, title from documents where id in ({placeholders})"
    params: List[object] = list(unique_ids)
    if user_id is not None:
        sql += " and user_id = ?"
        params.append(user_id)

    with sqlite3.connect(_DB_PATH) as conn:
        rows = conn.execute(sql, params).fetchall()
    return {row[0]: row[1] for row in rows}


def _title_boost(query_variants: List[str], document_title: str) -> float:
    """若法规标题直接命中归一化查询，则给予显式加权"""
    normalized_title = normalize_query_text(document_title or "").replace(" ", "")
    if not normalized_title:
        return 0.0

    best_boost = 0.0
    for variant in query_variants:
        compact_variant = normalize_query_text(variant).replace(" ", "")
        if not compact_variant:
            continue
        if compact_variant in normalized_title:
            # 更长的命中查询给更高权重，避免宽泛标题误命中。
            boost = 0.03 + min(len(compact_variant), 12) * 0.001
            best_boost = max(best_boost, boost)
    return best_boost


def _focus_terms(query_variants: List[str]) -> List[str]:
    normalized_variants = [normalize_query_text(variant).replace(" ", "") for variant in query_variants]
    return [term for term in _LEGAL_HINT_TERMS if any(term in variant for variant in normalized_variants)]


def _chunk_title_boost(query_variants: List[str], chunk_title: str) -> float:
    normalized_title = normalize_query_text(chunk_title or "").replace(" ", "")
    if not normalized_title:
        return 0.0

    boost = 0.0
    for term in _focus_terms(query_variants):
        if term in normalized_title:
            boost += 0.01
    return min(boost, 0.03)


def search_with_variants(
    query: str,
    search_fn: Callable[[str], List[Dict]],
    top_k: int,
    user_id: Optional[int] = None,
    extra_queries: Optional[List[str]] = None,
) -> List[Dict]:
    """
    用多个轻量查询变体召回，再按标题命中重排。

    `search_fn` 负责执行单次底层搜索，返回按分数降序排列的结果。
    """
    query_variants: List[str] = []
    for raw_query in [query] + list(extra_queries or []):
        for variant in build_query_variants(raw_query):
            if variant not in query_variants:
                query_variants.append(variant)
    merged: Dict[str, Dict] = {}

    for variant in query_variants:
        for item in search_fn(variant):
            item_id = item.get("id")
            if not item_id:
                continue
            existing = merged.get(item_id)
            candidate = dict(item)
            if existing is None or candidate.get("score", 0.0) > existing.get("score", 0.0):
                merged[item_id] = candidate

    results = list(merged.values())
    if not results:
        return []

    doc_titles = get_document_titles(
        [item.get("document_id", "") for item in results if item.get("document_id")],
        user_id=user_id,
    )

    for item in results:
        boost = _title_boost(query_variants, doc_titles.get(item.get("document_id", ""), ""))
        chunk_boost = _chunk_title_boost(query_variants, item.get("title", ""))
        item["score"] = float(item.get("score", 0.0)) + boost + chunk_boost

    results.sort(key=lambda item: item.get("score", 0.0), reverse=True)

    if results:
        top_score = float(results[0].get("score", 0.0))
        focused_results = [item for item in results if float(item.get("score", 0.0)) >= top_score * 0.7]
        if top_score >= 0.03 and len(focused_results) >= 3:
            return focused_results[:top_k]

    return results[:top_k]
