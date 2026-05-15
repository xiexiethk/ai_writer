from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request, status

BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.auth import get_user_by_token
from app.core.database import AsyncSessionLocal


def resolve_request_token(request: Request) -> str | None:
    auth_header = str(request.headers.get("Authorization") or "").strip()
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        if token:
            return token
    query_token = str(request.query_params.get("token") or "").strip()
    return query_token or None


async def authenticate_request(request: Request):
    token = resolve_request_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少登录令牌",
        )

    async with AsyncSessionLocal() as db:
        return await get_user_by_token(token, db)


def attach_user_context(body: Any, request: Request) -> Any:
    if not hasattr(body, "context"):
        return body
    context = dict(getattr(body, "context", {}) or {})
    current_user = getattr(request.state, "ai_writer_user", None)
    if current_user is not None:
        context["aiWriterUserId"] = int(current_user.id)
        context["aiWriterUsername"] = str(current_user.username)
    body.context = context
    return body


def get_ai_writer_provider_seed() -> dict[str, Any] | None:
    try:
        from app.core.config import settings
    except Exception:
        return None

    endpoint = str(settings.DEEPSEEK_CHAT_BASE_URL or "").strip().rstrip("/")
    model = str(settings.DEEPSEEK_CHAT_MODEL or "").strip()
    api_key = str(settings.DEEPSEEK_API_KEY or "").strip()
    if not endpoint or not model:
        return None

    return {
        "id": "ai-writer-chat",
        "label": "AI Writer 默认模型",
        "endpoint": endpoint,
        "defaultModel": model,
        "apiKey": api_key,
        "isPreset": False,
        "supportsVision": False,
        "promptCacheMode": "off",
        "promptCacheRetention": "in_memory",
    }
