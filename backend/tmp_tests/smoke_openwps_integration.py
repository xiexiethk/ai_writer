from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.main import app
from app.core.database import AsyncSessionLocal
from app.models.document_db import Document
from openwps_server.app.ai import _parse_tool_result_payload, _run_knowledge_search_tool


async def register_and_login(client: httpx.AsyncClient) -> str:
    suffix = int(time.time())
    username = f"openwps_smoke_{suffix}"
    password = "Openwps123!"
    email = f"{username}@example.com"

    register_response = await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "username": username,
            "password": password,
            "is_superuser": False,
        },
    )
    assert register_response.status_code == 200, register_response.text

    login_response = await client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_response.status_code == 200, login_response.text
    token = login_response.json()["access_token"]
    assert token
    return token


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
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        token = await register_and_login(client)
        auth_headers = {"Authorization": f"Bearer {token}"}

        unauth_settings = await client.get("/openwps/api/ai/settings")
        assert unauth_settings.status_code == 401, unauth_settings.text

        openwps_index = await client.get("/openwps/")
        assert openwps_index.status_code == 200, openwps_index.text[:200]
        assert 'id="root"' in openwps_index.text

        settings_response = await client.get("/openwps/api/ai/settings", headers=auth_headers)
        assert settings_response.status_code == 200, settings_response.text
        settings_payload = settings_response.json()
        assert "providers" in settings_payload and settings_payload["providers"], settings_payload

        conversation_response = await client.post(
            "/openwps/api/conversations",
            json={"title": "Smoke Test Conversation"},
            headers=auth_headers,
        )
        assert conversation_response.status_code == 200, conversation_response.text
        conversation_id = conversation_response.json()["id"]
        assert conversation_id

        conversation_list = await client.get("/openwps/api/conversations", headers=auth_headers)
        assert conversation_list.status_code == 200, conversation_list.text
        assert any(item.get("id") == conversation_id for item in conversation_list.json())

        doc_info = await find_existing_chunked_document()
        assert doc_info is not None, "未找到可用于知识检索的已分块文档"
        user_id, document_id, document_title = doc_info
        query = (document_title or "文档").strip()[:12] or "文档"

        knowledge_result_raw = await _run_knowledge_search_tool(
            {"query": query, "documentId": document_id, "topK": 3},
            {"aiWriterUserId": user_id},
        )
        knowledge_result = _parse_tool_result_payload(knowledge_result_raw)
        assert knowledge_result.get("success") is True, json.dumps(knowledge_result, ensure_ascii=False)
        data = knowledge_result.get("data") or {}
        assert data.get("scope", {}).get("documentId") == document_id, data
        assert "results" in data, data

        print(
            json.dumps(
                {
                    "openwps_index": "ok",
                    "settings_active_provider": settings_payload.get("activeProviderId"),
                    "conversation_id": conversation_id,
                    "knowledge_chunks": len(data.get("results") or []),
                    "knowledge_document_id": document_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
