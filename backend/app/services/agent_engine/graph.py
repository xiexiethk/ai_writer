"""
Agent RAG Engine - LangGraph 图定义
工具选择、工具调用解析、工具执行循环全部放在 Agent 层；
底层模型仅作为 OpenAI-compatible /v1/chat/completions 文本推理服务。
"""
import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.graph import END, StateGraph

from app.services.agent_engine.prompts import AGENT_DECISION_JSON_SCHEMA, AGENT_SYSTEM_PROMPT
from app.services.agent_engine.state import AgentState
from app.services.agent_engine.tools import AGENT_TOOLS, infer_primary_search_tool
from app.services.rag import task_manager

logger = logging.getLogger(__name__)
SEARCH_TOOLS = {"t_direct_search", "t_step_back_search", "t_multi_query_search", "t_rewrite_search"}


def _tool_registry() -> dict[str, Any]:
    return {tool.name: tool for tool in AGENT_TOOLS}


def _escape_prompt_braces(text: str) -> str:
    return (text or "").replace("{", "{{").replace("}", "}}")


def _normalize_json_like_text(text: str) -> str:
    normalized = (text or "").strip()
    replacements = {
        "“": '"',
        "”": '"',
        "‘": '"',
        "’": '"',
        "：": ":",
        "，": ",",
        "【": "[",
        "】": "]",
        "（": "(",
        "）": ")",
    }
    for src, target in replacements.items():
        normalized = normalized.replace(src, target)
    normalized = re.sub(r",(\s*[}\]])", r"\1", normalized)
    return normalized


def _extract_field_with_regex(text: str, field: str) -> Optional[str]:
    pattern = rf'["“]{re.escape(field)}["”]\s*[:：]\s*(.+?)(?:,\s*["“][A-Za-z_]+["”]\s*[:：]|[}}\n]\s*$)'
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip().rstrip(",")
    if value in {"null", "None"}:
        return None
    if len(value) >= 2 and value[0] in {'"', "'"} and value[-1] == value[0]:
        value = value[1:-1]
    return value.strip()


def _parse_decision_payload(raw_text: str) -> dict[str, Any]:
    text = (raw_text or "").strip()
    if not text:
        return {"thought": "模型未返回可解析决策。", "action": "final", "tool_name": None, "tool_input": {}, "answer": "未生成有效回答。"}
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return {
                "thought": parsed.get("thought") or "",
                "action": (parsed.get("action") or "final").strip().lower(),
                "tool_name": parsed.get("tool_name"),
                "tool_input": parsed.get("tool_input") or {},
                "answer": parsed.get("answer"),
            }
    except Exception:
        normalized = _normalize_json_like_text(text)
        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return {
                    "thought": parsed.get("thought") or "",
                    "action": (parsed.get("action") or "final").strip().lower(),
                    "tool_name": parsed.get("tool_name"),
                    "tool_input": parsed.get("tool_input") or {},
                    "answer": parsed.get("answer"),
                }
        except Exception:
            thought = _extract_field_with_regex(text, "thought") or ""
            action = (_extract_field_with_regex(text, "action") or "final").strip().lower()
            tool_name = _extract_field_with_regex(text, "tool_name")
            answer = _extract_field_with_regex(text, "answer")
            if thought or answer or tool_name or action != "final":
                return {
                    "thought": thought,
                    "action": action if action in {"tool", "final"} else "final",
                    "tool_name": tool_name,
                    "tool_input": {},
                    "answer": answer,
                }
    return {"thought": "模型返回非 JSON，按最终答案处理。", "action": "final", "tool_name": None, "tool_input": {}, "answer": text}


def _build_chat_history(messages: List[Any]) -> List[Dict[str, str]]:
    history: List[Dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history.append({"role": "user", "content": getattr(msg, "content", "")})
        elif isinstance(msg, AIMessage):
            history.append({"role": "assistant", "content": getattr(msg, "content", "")})
    return history


def _messages_brief(messages: List[Any], limit: int = 8) -> List[Dict[str, str]]:
    return _build_chat_history(messages)[-limit:]


def _last_tool_name(messages: List[Any]) -> Optional[str]:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = getattr(msg, "content", "") or ""
            if content.startswith("[Tool:") and "]" in content:
                return content.split("]", 1)[0].removeprefix("[Tool:")
    return None


async def _run_model_decision(llm, state: AgentState) -> dict[str, Any]:
    messages = list(state.get("messages", []))
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            AGENT_SYSTEM_PROMPT
            + "\n\n你必须只输出一个 JSON 对象，严格遵循以下 schema，不要输出额外文字：\n"
            + _escape_prompt_braces(AGENT_DECISION_JSON_SCHEMA)
            + "\n\n补充规则：\n"
            + "1. action 只能是 tool 或 final。\n"
            + "2. 如果 action=tool，则 tool_name 必须是可用工具之一。\n"
            + "3. 如果已达到最大检索次数，必须输出 final。\n"
            + "4. 若 observation 已足够，优先 final，不要重复检索。"
        ),
        MessagesPlaceholder(variable_name="messages"),
        (
            "human",
            "上下文摘要(JSON)：\n{meta_json}\n\n请输出下一步决策 JSON。"
        ),
    ])
    meta_json = json.dumps(
        {
            "available_tools": [tool.name for tool in AGENT_TOOLS],
            "search_count": int(state.get("search_count", 0) or 0),
            "max_search_count": int(state.get("max_search_count", 0) or 0),
            "recent_messages": _messages_brief(messages),
            "document_ids_count": len(state.get("document_ids") or []),
        },
        ensure_ascii=False,
    )
    chain = prompt | llm | StrOutputParser()
    raw = await chain.ainvoke({"messages": messages, "meta_json": meta_json})
    return _parse_decision_payload(raw)


async def _execute_tool(tool_name: str, tool_input: dict, state: AgentState) -> tuple[str, List[dict], int]:
    tools = _tool_registry()
    if tool_name not in tools:
        raise ValueError(f"未知工具: {tool_name}")

    from app.services.agent_engine.prompts import MULTI_QUERY_GENERATION_PROMPT, REWRITE_GENERATION_PROMPT, STEP_BACK_GENERATION_PROMPT
    from app.services.agent_engine.tools import _execute_search_with_results, _get_tool_llm

    user_id = state.get("user_id")
    document_ids = state.get("document_ids")
    original_question = state.get("original_question")
    query = (tool_input or {}).get("query", "")
    chat_history = _build_chat_history(list(state.get("messages", [])))[:-1]

    if tool_name == "t_direct_search":
        text, raw = await asyncio.to_thread(_execute_search_with_results, query, 8, document_ids, user_id, original_question)
        return text, raw, 1

    if tool_name == "t_step_back_search":
        llm = _get_tool_llm()
        chain = ChatPromptTemplate.from_template(STEP_BACK_GENERATION_PROMPT) | llm | StrOutputParser()
        abstract_query = (await chain.ainvoke({"question": query})).strip() or query
        concrete_text, concrete_raw = await asyncio.to_thread(_execute_search_with_results, query, 3, document_ids, user_id, original_question)
        abstract_text, abstract_raw = await asyncio.to_thread(_execute_search_with_results, abstract_query, 3, document_ids, user_id, original_question)
        return f"【具体细节】\n{concrete_text}\n\n【背景知识】\n{abstract_text}", concrete_raw + abstract_raw, 1

    if tool_name == "t_multi_query_search":
        llm = _get_tool_llm()
        chain = ChatPromptTemplate.from_template(MULTI_QUERY_GENERATION_PROMPT) | llm | StrOutputParser()
        queries = [q.strip() for q in (await chain.ainvoke({"question": query})).strip().split("\n") if q.strip()] or [query]
        parts: List[str] = []
        raws: List[dict] = []
        for idx, q in enumerate(queries[:3], start=1):
            res_text, res_raw = await asyncio.to_thread(_execute_search_with_results, q, 2, document_ids, user_id, original_question)
            parts.append(f"【视角{idx}: {q}】\n{res_text}")
            raws.extend(res_raw)
        return "\n\n".join(parts), raws, 1

    if tool_name == "t_rewrite_search":
        history_str = "\n".join([f"[{item['role']}: {item['content']}]" for item in chat_history[-10:]])
        llm = _get_tool_llm()
        chain = ChatPromptTemplate.from_template(REWRITE_GENERATION_PROMPT) | llm | StrOutputParser()
        rewritten = (await chain.ainvoke({"question": query, "chat_history": history_str})).strip() or query
        res_text, res_raw = await asyncio.to_thread(_execute_search_with_results, rewritten, 8, document_ids, user_id, original_question)
        return f"【重写后的查询: {rewritten}】\n\n{res_text}", res_raw, 1

    tool = tools[tool_name]
    result = await tool.ainvoke(tool_input or {})
    return str(result), [], 0


def _route_after_agent(state: AgentState) -> str:
    return "tools" if state.get("pending_tool_name") else END


def build_agent_graph(llm):
    async def agent_node(state: AgentState) -> dict:
        task_id = state.get("task_id")
        if task_id and task_manager.is_task_stopped(task_id):
            return {
                "messages": [AIMessage(content="任务已被用户停止。")],
                "steps": [{"type": "answer", "content": "任务已被用户停止。", "status": "error", "timestamp": time.time()}],
                "final_answer": "任务已被用户停止。",
                "pending_tool_name": None,
                "pending_tool_input": None,
            }

        document_ids = state.get("document_ids") or []
        original_question = state.get("original_question") or ""
        search_count = int(state.get("search_count", 0) or 0)
        max_search_count = int(state.get("max_search_count", 0) or 0)

        if search_count == 0 and document_ids:
            primary = infer_primary_search_tool(original_question, document_ids=document_ids)
            if primary:
                thought = "首轮按问题结构触发主检索。"
                return {
                    "messages": [AIMessage(content=thought)],
                    "steps": [{"type": "thought", "content": thought, "status": "success", "timestamp": time.time()}],
                    "pending_tool_name": primary,
                    "pending_tool_input": {"query": original_question},
                    "final_answer": None,
                }

        if max_search_count and search_count >= max_search_count:
            decision = {"thought": "已达到最大检索次数，直接输出最终答案。", "action": "final", "tool_name": None, "tool_input": {}, "answer": None}
        else:
            decision = await _run_model_decision(llm, state)

        thought = decision.get("thought") or "完成当前轮决策。"
        action = (decision.get("action") or "final").strip().lower()
        tool_name = decision.get("tool_name")
        tool_input = decision.get("tool_input") or {}
        answer = decision.get("answer")

        last_tool = _last_tool_name(list(state.get("messages", [])))
        if action == "tool" and tool_name in _tool_registry():
            if tool_name in SEARCH_TOOLS and last_tool == tool_name and search_count > 0:
                final_answer = answer or f"{thought}\n\n已避免重复调用同一检索工具，基于现有结果直接收敛回答。"
                return {
                    "messages": [AIMessage(content=final_answer)],
                    "steps": [{"type": "answer", "content": "避免重复检索，直接生成最终答案", "status": "success", "timestamp": time.time()}],
                    "pending_tool_name": None,
                    "pending_tool_input": None,
                    "final_answer": final_answer,
                }
            return {
                "messages": [AIMessage(content=thought)],
                "steps": [{"type": "thought", "content": thought, "status": "success", "timestamp": time.time()}],
                "pending_tool_name": tool_name,
                "pending_tool_input": tool_input,
                "final_answer": None,
            }

        if action == "tool" and tool_name not in _tool_registry():
            thought = f"{thought}\n\n模型给出了非法工具名 {tool_name}，已降级为直接输出答案。"
        final_answer = answer or thought or "未生成有效回答。"
        return {
            "messages": [AIMessage(content=final_answer)],
            "steps": [{"type": "answer", "content": "生成最终答案", "status": "success", "timestamp": time.time()}],
            "pending_tool_name": None,
            "pending_tool_input": None,
            "final_answer": final_answer,
        }

    async def tool_node(state: AgentState) -> dict:
        tool_name = state.get("pending_tool_name")
        tool_input = state.get("pending_tool_input") or {}
        if not tool_name:
            return {"pending_tool_name": None, "pending_tool_input": None}
        action_step = {
            "type": "action",
            "content": f"调用工具: {tool_name}",
            "tool": tool_name,
            "status": "pending",
            "timestamp": time.time(),
            "details": {"input": dict(tool_input)},
        }
        try:
            result_text, raw_sources, search_inc = await _execute_tool(tool_name, tool_input, state)
            action_step["status"] = "success"
            observation_step = {
                "type": "observation",
                "content": f"工具返回结果摘要: {(result_text[:500] + '...') if len(result_text) > 500 else result_text}",
                "tool": tool_name,
                "status": "success",
                "timestamp": time.time(),
                "details": {"output": {"count": len(raw_sources), "chunks": raw_sources}},
            }
            return {
                "messages": [AIMessage(content=f"[Tool:{tool_name}]\n{result_text}")],
                "steps": [action_step, observation_step],
                "sources": raw_sources or None,
                "search_count": int(state.get("search_count", 0) or 0) + int(search_inc or 0),
                "pending_tool_name": None,
                "pending_tool_input": None,
            }
        except Exception as exc:
            action_step["status"] = "error"
            action_step["content"] = f"工具执行失败: {exc}"
            return {
                "messages": [AIMessage(content=f"工具 {tool_name} 执行失败: {exc}")],
                "steps": [action_step],
                "pending_tool_name": None,
                "pending_tool_input": None,
            }

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("tools", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges("agent", _route_after_agent, {"tools": "tools", END: END})
    workflow.add_edge("tools", "agent")
    return workflow.compile()
