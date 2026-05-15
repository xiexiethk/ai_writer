"""
报告生成模块的多轮写作会话服务。
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.document_db import Document
from app.models.document_project import document_project_storage
from app.services.hybrid_rag_service import hybrid_rag_service
from app.services.llm_gateway import (
    chat_completion_async,
    resolve_chat_model,
    resolve_chat_provider,
)
from app.services.report_memory_store import report_memory_store

logger = logging.getLogger(__name__)


class ReportConversationService:
    """管理报告项目的项目级/章节级写作会话。"""

    def __init__(
        self,
        provider: Optional[str] = None,
        llm_model: Optional[str] = None,
    ):
        self.provider = resolve_chat_provider(provider)
        self.llm_model = resolve_chat_model(self.provider, llm_model)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        other_chars = max(0, len(text) - chinese_chars)
        return max(1, chinese_chars + other_chars // 4) if text else 0

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        if not text or max_tokens <= 0:
            return ""
        if self._estimate_tokens(text) <= max_tokens:
            return text

        low = 0
        high = len(text)
        best = ""
        suffix = "..."
        while low <= high:
            middle = (low + high) // 2
            candidate = text[:middle].rstrip() + suffix
            if self._estimate_tokens(candidate) <= max_tokens:
                best = candidate
                low = middle + 1
            else:
                high = middle - 1
        return best or text[: max(1, min(len(text), max_tokens))].rstrip() + suffix

    def _format_outline(self, nodes: Sequence[Dict[str, Any]], indent: int = 0, limit: int = 60) -> Tuple[str, int]:
        lines: List[str] = []
        count = 0

        def walk(children: Sequence[Dict[str, Any]], depth: int) -> None:
            nonlocal count
            for child in children:
                if count >= limit:
                    return
                label = child.get("label", "无标题")
                lines.append(f"{'  ' * depth}- {label}")
                count += 1
                if child.get("children"):
                    walk(child["children"], depth + 1)

        walk(nodes, indent)
        return "\n".join(lines), count

    def _find_outline_path(
        self,
        nodes: Sequence[Dict[str, Any]],
        target_id: str,
        path: Optional[List[str]] = None,
    ) -> List[str]:
        current_path = path or []
        for node in nodes:
            next_path = current_path + [node.get("label", "无标题")]
            if node.get("id") == target_id:
                return next_path
            children = node.get("children") or []
            if children:
                found = self._find_outline_path(children, target_id, next_path)
                if found:
                    return found
        return []

    def _section_context(
        self,
        project: Dict[str, Any],
        section_id: Optional[str],
    ) -> Tuple[Optional[str], List[str], str]:
        if not section_id:
            return None, [], ""

        path = self._find_outline_path(project.get("outline", []), section_id)
        title = path[-1] if path else section_id
        section_data = project.get("sections", {}).get(section_id, {})
        paragraphs = section_data.get("paragraphs", [])
        current_content = paragraphs[-1].get("content", "") if paragraphs else ""
        current_content = self._truncate_to_tokens(current_content, 900)

        context = [f"目标章节: {title}"]
        if path:
            context.append(f"章节路径: {' > '.join(path)}")
        if current_content:
            context.append(f"当前正文:\n{current_content}")

        return title, path, "\n".join(context)

    async def _decorate_sources(self, chunks: Sequence[Dict[str, Any]], user_id: Optional[int]) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        doc_ids = {chunk.get("document_id") for chunk in chunks if chunk.get("document_id")}
        doc_names: Dict[str, str] = {}
        if doc_ids:
            try:
                async with AsyncSessionLocal() as db:
                    query = select(Document.id, Document.title).where(Document.id.in_(list(doc_ids)))
                    if user_id is not None:
                        query = query.where(Document.user_id == user_id)
                    rows = await db.execute(query)
                    doc_names = {row[0]: row[1] for row in rows.all()}
            except Exception as exc:
                logger.warning("批量获取报告会话来源文档名称失败: %s", exc)

        return [
            {
                "id": str(chunk.get("id", "")),
                "document_id": chunk.get("document_id", ""),
                "document_name": doc_names.get(chunk.get("document_id", ""), "未知文档"),
                "title": chunk.get("title", ""),
                "content": chunk.get("content", ""),
                "score": chunk.get("score", 0.0),
                "chunk_index": chunk.get("chunk_index", 0),
                "level": chunk.get("level", 0),
            }
            for chunk in chunks
        ]

    async def _retrieve_sources(
        self,
        *,
        query: str,
        user_id: Optional[int],
        document_ids: Optional[List[str]],
        top_k: int = 4,
    ) -> List[Dict[str, Any]]:
        if not query.strip() or not user_id or not document_ids:
            return []

        try:
            raw_chunks = await hybrid_rag_service.hybrid_search(
                query=query,
                user_id=user_id,
                document_ids=document_ids,
                top_k=top_k,
                mode="report_edit",
            )
        except Exception as exc:
            logger.warning("报告会话文档检索失败，降级为空来源: %s", exc)
            return []

        filtered_chunks = [chunk for chunk in raw_chunks if chunk.get("score", 0.0) >= 0.15]
        return await self._decorate_sources(filtered_chunks[:top_k], user_id)

    def _messages_to_summary_text(self, messages: Sequence[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for message in messages:
            role = "用户" if message.get("role") == "user" else "助手"
            content = self._truncate_to_tokens(message.get("content", ""), 350)
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    async def _generate_summary(
        self,
        existing_summary: str,
        messages_to_compact: Sequence[Dict[str, Any]],
    ) -> str:
        history_text = self._messages_to_summary_text(messages_to_compact)
        if not history_text.strip():
            return existing_summary

        prompt = (
            "请为报告写作助手维护一份滚动记忆摘要。"
            "输出中文 Markdown，严格包含以下小节：\n"
            "## 用户目标\n"
            "## 已确认约束\n"
            "## 已采纳修改\n"
            "## 未决问题\n"
            "## 风格要求\n"
            "## 关键事实与引用\n\n"
            "要求：只保留后续写作对话真正需要记住的信息，删除重复措辞和闲聊。\n\n"
            f"现有摘要：\n{existing_summary or '（无）'}\n\n"
            f"新增历史对话：\n{history_text}\n"
        )

        try:
            return (
                await chat_completion_async(
                provider=self.provider,
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "你是严谨的对话记忆压缩器，只输出可供后续模型使用的结构化摘要。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                top_p=0.9,
                max_tokens=600,
                timeout=120.0,
                )
            ).strip()
        except Exception as exc:
            logger.warning("报告会话滚动摘要生成失败，保留原始摘要: %s", exc)
            return existing_summary

    async def _maybe_compact_conversation(
        self,
        project_id: str,
        conversation: Dict[str, Any],
        user_id: Optional[int],
    ) -> Dict[str, Any]:
        messages = conversation.get("messages", [])
        if not messages:
            return conversation

        context_config = conversation.get("contextConfig", {})
        recent_window = int(conversation.get("recentWindow") or context_config.get("recentTurns", 3) or 3)
        compacted_count = int(conversation.get("compactedMessageCount", 0) or 0)
        token_budget = int(conversation.get("tokenBudget", 6000) or 6000)
        trigger_ratio = float(context_config.get("summaryTriggerRatio", 0.8) or 0.8)

        if len(messages) - compacted_count <= recent_window + 2:
            return conversation

        pending_messages = messages[compacted_count:]
        pending_tokens = sum(
            int(message.get("tokenEstimate") or self._estimate_tokens(message.get("content", "")))
            for message in pending_messages
        )
        if pending_tokens < int(token_budget * trigger_ratio):
            return conversation

        cutoff = len(messages) - recent_window
        if cutoff <= compacted_count:
            return conversation

        messages_to_compact = messages[compacted_count:cutoff]
        summary = await self._generate_summary(
            conversation.get("rollingSummary", ""),
            messages_to_compact,
        )
        new_version = int(conversation.get("summaryVersion", 0) or 0) + 1
        memory_status = dict(conversation.get("memoryStatus", {}))
        memory_status["lastSummaryIndexedAt"] = self._now_iso()

        updated = document_project_storage.update_conversation(
            project_id,
            conversation["id"],
            rollingSummary=summary,
            summaryVersion=new_version,
            compactedMessageCount=cutoff,
            lastCompactedAt=self._now_iso(),
            memoryStatus=memory_status,
        )
        if updated:
            await report_memory_store.store_summary_async(
                project_id,
                conversation["id"],
                conversation.get("scopeType", "project"),
                conversation.get("scopeId", project_id),
                summary,
                new_version,
                user_id=user_id,
            )
            return updated
        return conversation

    def _recent_messages(self, conversation: Dict[str, Any]) -> List[Dict[str, Any]]:
        messages = conversation.get("messages", [])
        compacted_count = int(conversation.get("compactedMessageCount", 0) or 0)
        recent_window = int(
            conversation.get("recentWindow")
            or conversation.get("contextConfig", {}).get("recentTurns", 3)
            or 3
        )
        start_index = max(compacted_count, len(messages) - recent_window)
        return messages[start_index:]

    def _format_sources_for_prompt(self, sources: Sequence[Dict[str, Any]]) -> str:
        parts = []
        for index, source in enumerate(sources, start=1):
            content = self._truncate_to_tokens(source.get("content", ""), 320)
            parts.append(
                f"[来源{index}] 文档: {source.get('document_name', '未知文档')}\n"
                f"章节: {source.get('title', '')}\n"
                f"相关度: {source.get('score', 0.0):.4f}\n"
                f"内容: {content}"
            )
        return "\n\n".join(parts)

    def _format_memories_for_prompt(self, memories: Sequence[Dict[str, Any]]) -> str:
        parts = []
        for index, memory in enumerate(memories, start=1):
            parts.append(
                f"[记忆{index}] 类型: {memory.get('memory_type', 'turn')}, 角色: {memory.get('role', 'unknown')}\n"
                f"内容: {memory.get('content', '')}"
            )
        return "\n\n".join(parts)

    def _system_prompt(
        self,
        *,
        scope_type: str,
        apply_mode: str,
        section_title: Optional[str],
    ) -> str:
        if apply_mode == "apply_to_section":
            title_hint = f"《{section_title}》" if section_title else "目标章节"
            return (
                "你是严谨的中文报告写作助手。\n"
                f"当前任务是直接改写 {title_hint} 的正文。\n"
                "必须遵守：\n"
                "1. 只输出最终可落库的章节正文，不要解释，不要标题，不要 Markdown 代码块。\n"
                "2. 优先复用知识库参考和对话已确认约束，避免编造事实。\n"
                "3. 如果用户要求修改风格、结构或重点，直接体现在正文里。\n"
                "4. 保持书面、严谨、逻辑清晰的中文表述。"
            )

        scope_hint = "整份报告" if scope_type == "project" else "当前章节"
        return (
            "你是严谨的中文报告写作助手。\n"
            f"当前任务聚焦于{scope_hint}的持续写作与修改建议。\n"
            "必须遵守：\n"
            "1. 优先基于知识库参考、滚动摘要和已确认约束回答。\n"
            "2. 给出可执行建议；如果提供建议稿或改写稿，要明确指出适用章节。\n"
            "3. 控制冗余，优先输出对下一步写作真正有帮助的信息。"
        )

    def _build_completion_messages(
        self,
        *,
        project: Dict[str, Any],
        conversation: Dict[str, Any],
        user_input: str,
        apply_mode: str,
        target_section_id: Optional[str],
        section_title: Optional[str],
        section_path: Sequence[str],
        section_context: str,
        recent_messages: Sequence[Dict[str, Any]],
        retrieved_memories: Sequence[Dict[str, Any]],
        sources: Sequence[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        token_budget = int(conversation.get("tokenBudget", 6000) or 6000)
        outline_text, outline_count = self._format_outline(project.get("outline", []))
        project_snapshot = (
            f"项目标题: {project.get('title', '未命名项目')}\n"
            f"知识库数量: {len(project.get('folderIds', []))}\n"
            f"大纲节点数: {outline_count}\n"
            f"完整大纲:\n{outline_text}"
        )

        messages: List[Dict[str, str]] = []
        context_meta = {
            "usedSummary": bool(conversation.get("rollingSummary")),
            "recentTurns": 0,
            "retrievedMemories": len(retrieved_memories),
            "truncated": False,
            "estimatedInputTokens": 0,
        }
        used_tokens = 0

        def append_block(role: str, content: str, max_tokens: int) -> None:
            nonlocal used_tokens
            if not content.strip():
                return
            remaining_budget = token_budget - used_tokens - 400
            if remaining_budget <= 80:
                context_meta["truncated"] = True
                return
            effective_budget = min(max_tokens, remaining_budget)
            truncated = self._truncate_to_tokens(content, effective_budget)
            if truncated != content or effective_budget < max_tokens:
                context_meta["truncated"] = True
            if not truncated.strip():
                return
            messages.append({"role": role, "content": truncated})
            used_tokens += self._estimate_tokens(truncated)

        append_block(
            "system",
            self._system_prompt(
                scope_type=conversation.get("scopeType", "project"),
                apply_mode=apply_mode,
                section_title=section_title,
            ),
            700,
        )
        append_block("system", f"项目上下文：\n{project_snapshot}", 1200)
        if section_context:
            append_block("system", f"当前编辑目标：\n{section_context}", 1200)
        if conversation.get("rollingSummary"):
            append_block("system", f"滚动摘要：\n{conversation.get('rollingSummary', '')}", 900)
        if retrieved_memories:
            append_block("system", f"按需召回记忆：\n{self._format_memories_for_prompt(retrieved_memories)}", 700)
        if sources:
            append_block("system", f"知识库参考资料：\n{self._format_sources_for_prompt(sources)}", 1400)
        user_instruction = [f"用户本轮请求：{user_input.strip()}"]
        if section_path:
            user_instruction.append(f"章节路径：{' > '.join(section_path)}")
        if apply_mode == "apply_to_section":
            user_instruction.append("请直接输出可替换到目标章节中的最终正文。")
        else:
            user_instruction.append("请给出对当前写作最有帮助的回答。")
        user_prompt = "\n".join(user_instruction)
        user_tokens = self._estimate_tokens(user_prompt)

        remaining_for_recent = max(0, token_budget - used_tokens - user_tokens - 200)
        selected_recent: List[Dict[str, str]] = []
        for message in reversed(recent_messages):
            message_content = message.get("content", "")
            message_tokens = int(message.get("tokenEstimate") or self._estimate_tokens(message_content))
            if message_tokens <= remaining_for_recent:
                selected_recent.append({"role": message.get("role", "assistant"), "content": message_content})
                remaining_for_recent -= message_tokens
                continue

            if not selected_recent and remaining_for_recent > 120:
                truncated_content = self._truncate_to_tokens(message_content, remaining_for_recent)
                selected_recent.append({"role": message.get("role", "assistant"), "content": truncated_content})
                context_meta["truncated"] = True
                remaining_for_recent = 0
            break

        selected_recent.reverse()
        context_meta["recentTurns"] = len(selected_recent)
        messages.extend(selected_recent)
        messages.append({"role": "user", "content": user_prompt})
        context_meta["estimatedInputTokens"] = sum(self._estimate_tokens(item["content"]) for item in messages)
        return messages, context_meta

    def create_conversation(
        self,
        *,
        project_id: str,
        scope_type: str,
        scope_id: str,
        title: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        resolved_title = title or ("项目写作助手" if scope_type == "project" else "章节写作助手")
        return document_project_storage.create_conversation(
            project_id=project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            title=resolved_title,
            user_id=user_id,
        )

    def list_conversations(
        self,
        *,
        project_id: str,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return document_project_storage.list_conversations(
            project_id=project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            user_id=user_id,
        )

    def get_conversation(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        return document_project_storage.get_conversation(
            project_id,
            conversation_id,
            user_id=user_id,
        )

    async def send_message(
        self,
        *,
        project_id: str,
        conversation_id: str,
        user_input: str,
        apply_mode: str = "suggest_only",
        target_section_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        project = document_project_storage.get_project(project_id, user_id=user_id)
        if not project:
            raise ValueError("项目不存在")

        conversation = document_project_storage.get_conversation(
            project_id,
            conversation_id,
            user_id=user_id,
        )
        if not conversation:
            raise ValueError("会话不存在")

        conversation = await self._maybe_compact_conversation(project_id, conversation, user_id)

        scope_type = conversation.get("scopeType", "project")
        resolved_target_section_id = target_section_id
        if not resolved_target_section_id and scope_type == "section":
            resolved_target_section_id = conversation.get("scopeId")
        if apply_mode == "apply_to_section" and not resolved_target_section_id:
            apply_mode = "suggest_only"

        section_title, section_path, section_context = self._section_context(project, resolved_target_section_id)
        recent_messages = self._recent_messages(conversation)
        recent_message_ids = [message.get("id") for message in recent_messages if message.get("id")]

        retrieval_query_parts = [user_input.strip()]
        if section_path:
            retrieval_query_parts.insert(0, " > ".join(section_path))
        elif project.get("title"):
            retrieval_query_parts.insert(0, project["title"])
        retrieval_query = "\n".join(part for part in retrieval_query_parts if part)

        retrieved_memories = await report_memory_store.search_async(
            project_id,
            retrieval_query,
            conversation_id=conversation_id,
            scope_type=scope_type,
            scope_id=conversation.get("scopeId"),
            top_k=int(conversation.get("contextConfig", {}).get("retrievedMemories", 3) or 3),
            exclude_message_ids=recent_message_ids,
        )

        sources = await self._retrieve_sources(
            query=retrieval_query,
            user_id=user_id,
            document_ids=document_ids,
            top_k=int(conversation.get("contextConfig", {}).get("maxSourceChunks", 4) or 4),
        )

        completion_messages, context_meta = self._build_completion_messages(
            project=project,
            conversation=conversation,
            user_input=user_input,
            apply_mode=apply_mode,
            target_section_id=resolved_target_section_id,
            section_title=section_title,
            section_path=section_path,
            section_context=section_context,
            recent_messages=recent_messages,
            retrieved_memories=retrieved_memories,
            sources=sources,
        )

        assistant_content = (
            await chat_completion_async(
                provider=self.provider,
                model=self.llm_model,
                messages=completion_messages,
                temperature=0.4 if apply_mode == "apply_to_section" else 0.6,
                top_p=0.9,
                max_tokens=1800,
                timeout=180.0,
            )
        ).strip()

        timestamp = self._now_iso()
        user_message = {
            "id": str(uuid.uuid4()),
            "role": "user",
            "content": user_input,
            "intentType": "report_edit",
            "appliedOperation": apply_mode,
            "tokenEstimate": self._estimate_tokens(user_input),
            "sourceRefs": [],
            "costTrace": {},
            "summaryEligible": True,
            "timestamp": timestamp,
        }
        document_project_storage.add_conversation_message(
            project_id,
            conversation_id,
            user_message,
            user_id=user_id,
        )

        applied_paragraph = None
        if apply_mode == "apply_to_section" and resolved_target_section_id:
            applied_paragraph = document_project_storage.replace_section_paragraph(
                project_id=project_id,
                section_id=resolved_target_section_id,
                content=assistant_content,
                sources=sources,
                user_id=user_id,
            )

        assistant_message = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": assistant_content,
            "intentType": "report_edit",
            "appliedOperation": "apply_to_section" if applied_paragraph else "suggest_only",
            "tokenEstimate": self._estimate_tokens(assistant_content),
            "sourceRefs": [source.get("id") for source in sources if source.get("id")],
            "sources": sources,
            "costTrace": {
                "model": self.llm_model,
                "estimatedInputTokens": context_meta.get("estimatedInputTokens", 0),
                "strategy": "rolling_summary+recent_turns+retrieved_memories+doc_sources",
            },
            "summaryEligible": True,
            "contextMeta": context_meta,
            "timestamp": self._now_iso(),
        }
        document_project_storage.add_conversation_message(
            project_id,
            conversation_id,
            assistant_message,
            user_id=user_id,
        )

        await report_memory_store.store_messages_async(
            project_id=project_id,
            conversation_id=conversation_id,
            scope_type=scope_type,
            scope_id=conversation.get("scopeId", project_id),
            messages=[user_message, assistant_message],
            user_id=user_id,
            memory_type="turn",
        )

        refreshed_conversation = document_project_storage.get_conversation(
            project_id,
            conversation_id,
            user_id=user_id,
        )
        memory_status = dict((refreshed_conversation or conversation).get("memoryStatus", {}))
        memory_status["lastIndexedAt"] = self._now_iso()
        memory_status["lastRetrievedAt"] = self._now_iso()
        memory_status["lastRetrievedCount"] = len(retrieved_memories)
        refreshed_conversation = document_project_storage.update_conversation(
            project_id,
            conversation_id,
            user_id=user_id,
            memoryStatus=memory_status,
        )

        return {
            "assistant_message": assistant_message,
            "sources": sources,
            "context_meta": context_meta,
            "applied_paragraph": applied_paragraph,
            "conversation": refreshed_conversation,
        }


report_conversation_service = ReportConversationService()
