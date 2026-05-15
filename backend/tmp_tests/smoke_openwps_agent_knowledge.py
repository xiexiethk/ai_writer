from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.database import AsyncSessionLocal
from app.models.document_db import Document
from openwps_server.app.ai import ChatRequest, create_react_session, prepare_chat_request, stream_react_session


async def find_existing_chunked_document() -> tuple[int, str, str] | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Document.user_id, Document.id, Document.title)
            .where(Document.chunked == True)
            .limit(1)
        )
        row = result.first()
        if not row:
            vector_dir = BACKEND_ROOT / "data" / "vector_store_local"
            vector_file = next(vector_dir.glob("*.json"), None)
            if not vector_file:
                return None
            payload = json.loads(vector_file.read_text(encoding="utf-8"))
            document_id = str(payload.get("document_id") or vector_file.stem)
            chunks = payload.get("chunks") if isinstance(payload.get("chunks"), list) else []
            first_chunk = chunks[0] if chunks else {}
            title = str(first_chunk.get("title") or "").strip()
            if not title or title == "文档开头":
                title = str(first_chunk.get("content") or "文档").strip()[:24]
            return 1, document_id, title
        return int(row[0]), str(row[1]), str(row[2] or "")


async def main() -> None:
    doc_info = await find_existing_chunked_document()
    assert doc_info is not None, "未找到可用于 Agent 知识检索测试的已分块文档"
    user_id, document_id, document_title = doc_info
    query = (document_title or "文档").strip()[:12] or "文档"

    body = ChatRequest(
        message=(
            f"你必须先调用 knowledge_search 工具，查询“{query}”在当前知识库文档中的相关内容。"
            "工具调用成功后，只输出一行，以 TOOL_OK 开头，并简要说明命中了什么内容。"
        ),
        context={
            "aiWriterUserId": user_id,
            "knowledgeScope": {
                "documentId": document_id,
                "documentTitle": document_title,
            },
        },
        mode="agent",
        operationMode="build",
    )
    prepared_body = await prepare_chat_request(body)
    session = create_react_session(prepared_body)

    tool_result_payloads: list[dict] = []
    content_parts: list[str] = []

    async for event in stream_react_session(session):
        event_type = str(event.get("type") or "")
        if event_type == "content":
            content = str(event.get("content") or "")
            if content:
                content_parts.append(content)
        elif event_type == "tool_result" and event.get("name") == "knowledge_search":
            result = event.get("result") or {}
            payload = {
                "success": bool(result.get("success")),
                "message": str(result.get("message") or ""),
                "data": result.get("data"),
            }
            tool_result_payloads.append(payload)
        elif event_type == "error":
            raise AssertionError(str(event.get("message") or "Agent 执行失败"))

    assert tool_result_payloads, "Agent 未调用 knowledge_search 工具"
    assert any(item.get("success") for item in tool_result_payloads), json.dumps(tool_result_payloads, ensure_ascii=False)

    successful = next(item for item in tool_result_payloads if item.get("success"))
    scope = (successful.get("data") or {}).get("scope") or {}
    assert scope.get("documentId") == document_id, successful

    final_content = "".join(content_parts).strip()
    assert "TOOL_OK" in final_content, final_content

    print(
        json.dumps(
            {
                "knowledge_document_id": document_id,
                "knowledge_tool_calls": len(tool_result_payloads),
                "final_preview": final_content[:200],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
