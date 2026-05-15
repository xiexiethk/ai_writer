"""
统一的模型调用网关。
使用 DeepSeek API 作为聊天提供方，OpenAI API 作为 Embedding 提供方。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.network import create_async_httpx_client, create_httpx_client

logger = logging.getLogger(__name__)

DEEPSEEK_PROVIDER = "deepseek"
OPENAI_PROVIDER = "openai"

_CHAT_ALLOWED = {DEEPSEEK_PROVIDER}
_EMBEDDING_ALLOWED = {OPENAI_PROVIDER}

_THINK_BLOCK_RE = re.compile(r"<think\b[^>]*>.*?</think>", re.IGNORECASE | re.DOTALL)


def _normalize_provider(
    value: Optional[str],
    *,
    allowed: set[str],
    fallback: str,
) -> str:
    normalized = (value or fallback).strip().lower()
    if normalized in allowed:
        return normalized
    logger.warning("未知模型提供方 %s，回退到 %s", normalized, fallback)
    return fallback


def resolve_model_provider(provider: Optional[str] = None) -> str:
    return _normalize_provider(
        provider or settings.MODEL_PROVIDER,
        allowed=_CHAT_ALLOWED,
        fallback=DEEPSEEK_PROVIDER,
    )


def resolve_chat_provider(provider: Optional[str] = None) -> str:
    return _normalize_provider(
        provider or settings.CHAT_MODEL_PROVIDER or settings.MODEL_PROVIDER,
        allowed=_CHAT_ALLOWED,
        fallback=DEEPSEEK_PROVIDER,
    )


def resolve_embedding_provider(provider: Optional[str] = None) -> str:
    value = provider or settings.EMBEDDING_MODEL_PROVIDER or settings.MODEL_PROVIDER
    normalized = (value or OPENAI_PROVIDER).strip().lower()
    if normalized in _EMBEDDING_ALLOWED:
        return normalized
    logger.warning("未知 embedding provider %s，回退到 %s", normalized, OPENAI_PROVIDER)
    return OPENAI_PROVIDER


def resolve_chat_api_key(provider: Optional[str] = None) -> str:
    resolved_provider = resolve_chat_provider(provider)
    if resolved_provider == DEEPSEEK_PROVIDER:
        return settings.DEEPSEEK_API_KEY or ""
    return ""


def resolve_chat_thinking(provider: Optional[str] = None) -> Optional[dict[str, str]]:
    if resolve_chat_provider(provider) != DEEPSEEK_PROVIDER:
        return None
    thinking_type = (settings.DEEPSEEK_THINKING_TYPE or "").strip().lower()
    if thinking_type in {"", "disabled", "false", "0", "none", "off"}:
        return None
    return {"type": thinking_type}


def resolve_chat_base_url(provider: Optional[str] = None) -> str:
    resolved_provider = resolve_chat_provider(provider)
    if resolved_provider == DEEPSEEK_PROVIDER:
        return settings.DEEPSEEK_CHAT_BASE_URL.rstrip("/")
    return settings.DEEPSEEK_CHAT_BASE_URL.rstrip("/")


def resolve_embedding_base_url(provider: Optional[str] = None) -> str:
    resolved_provider = resolve_embedding_provider(provider)
    if resolved_provider == OPENAI_PROVIDER:
        return (
            settings.EMBEDDING_BASE_URL
            or settings.OPENAI_EMBEDDING_BASE_URL
            or "https://api.openai.com"
        ).rstrip("/")
    return (
        settings.EMBEDDING_BASE_URL
        or settings.OPENAI_EMBEDDING_BASE_URL
        or "https://api.openai.com"
    ).rstrip("/")


def resolve_chat_model(provider: Optional[str] = None, model: Optional[str] = None) -> str:
    if model:
        return model
    resolved_provider = resolve_chat_provider(provider)
    if resolved_provider == DEEPSEEK_PROVIDER:
        return settings.DEEPSEEK_CHAT_MODEL
    return settings.DEEPSEEK_CHAT_MODEL


def resolve_embedding_model(provider: Optional[str] = None, model: Optional[str] = None) -> str:
    if model:
        return model
    resolved_provider = resolve_embedding_provider(provider)
    if resolved_provider == OPENAI_PROVIDER:
        return settings.EMBEDDING_MODEL or settings.OPENAI_EMBEDDING_MODEL
    return settings.EMBEDDING_MODEL or settings.OPENAI_EMBEDDING_MODEL


def resolve_embedding_dimensions(provider: Optional[str] = None) -> Optional[int]:
    resolved_provider = resolve_embedding_provider(provider)
    if resolved_provider == OPENAI_PROVIDER:
        if settings.EMBEDDING_DIMENSIONS and settings.EMBEDDING_DIMENSIONS > 0:
            return settings.EMBEDDING_DIMENSIONS
        return settings.OPENAI_EMBEDDING_DIMENSIONS
    return None


def resolve_embedding_api_key(provider: Optional[str] = None) -> str:
    resolved_provider = resolve_embedding_provider(provider)
    if resolved_provider == OPENAI_PROVIDER:
        return settings.EMBEDDING_API_KEY or settings.OPENAI_API_KEY or settings.DEEPSEEK_API_KEY or ""
    return ""


def openai_compatible_base_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return normalized if normalized.endswith("/v1") else f"{normalized}/v1"


def openai_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def deepseek_headers() -> dict[str, str]:
    return openai_headers(settings.DEEPSEEK_API_KEY or "")


def openai_embedding_headers(provider: Optional[str] = None) -> dict[str, str]:
    return openai_headers(resolve_embedding_api_key(provider))


def is_openai_compatible_chat_provider(provider: Optional[str] = None) -> bool:
    return resolve_chat_provider(provider) == DEEPSEEK_PROVIDER


def embedding_model_note(model_name: Optional[str]) -> Optional[str]:
    normalized = (model_name or "").lower()
    if "text-embedding-3-small" in normalized:
        return "使用 OpenAI text-embedding-3-small（1536 维）"
    return None


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "".join(texts)
    return "" if content is None else str(content)


def strip_thinking_content(text: str) -> str:
    if not text:
        return text
    cleaned = _THINK_BLOCK_RE.sub("", text)
    cleaned = cleaned.replace("<think>", "").replace("</think>", "")
    return cleaned.strip()


def _build_chat_payload(
    model: str,
    messages: list[dict[str, Any]],
    temperature: Optional[float],
    top_p: Optional[float],
    max_tokens: Optional[int],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if top_p is not None:
        payload["top_p"] = top_p
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    thinking = resolve_chat_thinking(DEEPSEEK_PROVIDER)
    if thinking:
        payload["thinking"] = thinking
    return payload


def _build_embedding_payload(
    model: str,
    texts: str | list[str],
    dimensions: Optional[int],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "input": texts,
    }
    if dimensions is not None:
        payload["dimensions"] = dimensions
    return payload


def parse_chat_response(provider: str, payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message", {})
    return strip_thinking_content(_extract_text_content(message.get("content")))


def get_models(provider: Optional[str] = None, base_url: Optional[str] = None) -> list[str]:
    raw_provider = (provider or "").strip().lower()
    if raw_provider in _EMBEDDING_ALLOWED:
        resolved_provider = raw_provider
        resolved_base_url = (base_url or resolve_embedding_base_url(resolved_provider)).rstrip("/")
        headers = openai_embedding_headers(resolved_provider)
    else:
        resolved_provider = resolve_chat_provider(provider)
        resolved_base_url = (base_url or resolve_chat_base_url(resolved_provider)).rstrip("/")
        headers = deepseek_headers()

    try:
        with create_httpx_client(timeout=5.0) as client:
            response = client.get(f"{resolved_base_url}/models", headers=headers)
            response.raise_for_status()
            return [item.get("id", "") for item in response.json().get("data", []) if item.get("id")]
    except Exception:
        return []


def get_endpoint_status(
    *,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    model_name: Optional[str] = None,
) -> dict[str, Any]:
    raw_provider = (provider or "").strip().lower()
    if raw_provider in _EMBEDDING_ALLOWED:
        resolved_provider = raw_provider
        resolved_base_url = (base_url or resolve_embedding_base_url(resolved_provider)).rstrip("/")
    else:
        resolved_provider = resolve_chat_provider(provider)
        resolved_base_url = (base_url or resolve_chat_base_url(resolved_provider)).rstrip("/")
    models = get_models(resolved_provider, resolved_base_url)
    return {
        "provider": resolved_provider,
        "base_url": resolved_base_url,
        "running": bool(models),
        "model": model_name,
        "available_models": models,
        "note": embedding_model_note(model_name),
    }


def chat_completion(
    *,
    messages: list[dict[str, Any]],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 120.0,
) -> str:
    """同步聊天补全 - DeepSeek API。"""
    start_ts = time.time()
    resolved_provider = resolve_chat_provider(provider)
    resolved_model = resolve_chat_model(resolved_provider, model)
    resolved_base_url = resolve_chat_base_url(resolved_provider)
    logger.info(
        "chat_completion start provider=%s model=%s base_url=%s messages=%d temp=%s top_p=%s max_tokens=%s",
        resolved_provider,
        resolved_model,
        resolved_base_url,
        len(messages),
        temperature,
        top_p,
        max_tokens,
    )

    with create_httpx_client(timeout=timeout) as client:
        response = client.post(
            f"{resolved_base_url}/chat/completions",
            json=_build_chat_payload(resolved_model, messages, temperature, top_p, max_tokens),
            headers=deepseek_headers(),
        )
        response.raise_for_status()
        result = parse_chat_response(resolved_provider, response.json())
        logger.info(
            "chat_completion done provider=%s model=%s elapsed=%.2fs result_len=%d",
            resolved_provider,
            resolved_model,
            time.time() - start_ts,
            len(result or ""),
        )
        return result


async def chat_completion_async(
    *,
    messages: list[dict[str, Any]],
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float | httpx.Timeout = 120.0,
) -> str:
    """异步聊天补全 - DeepSeek API。"""
    start_ts = time.time()
    resolved_provider = resolve_chat_provider(provider)
    resolved_model = resolve_chat_model(resolved_provider, model)
    resolved_base_url = resolve_chat_base_url(resolved_provider)
    logger.info(
        "chat_completion_async start provider=%s model=%s base_url=%s messages=%d temp=%s top_p=%s max_tokens=%s",
        resolved_provider,
        resolved_model,
        resolved_base_url,
        len(messages),
        temperature,
        top_p,
        max_tokens,
    )

    async with create_async_httpx_client(timeout=timeout) as client:
        response = await client.post(
            f"{resolved_base_url}/chat/completions",
            json=_build_chat_payload(resolved_model, messages, temperature, top_p, max_tokens),
            headers=deepseek_headers(),
        )
        response.raise_for_status()
        result = parse_chat_response(resolved_provider, response.json())
        logger.info(
            "chat_completion_async done provider=%s model=%s elapsed=%.2fs result_len=%d",
            resolved_provider,
            resolved_model,
            time.time() - start_ts,
            len(result or ""),
        )
        return result


def embedding_request(
    texts: str | list[str],
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    timeout: float = 60.0,
) -> list[list[float]]:
    """同步 embedding 请求 - OpenAI API。"""
    start_ts = time.time()
    resolved_provider = resolve_embedding_provider(provider)
    resolved_model = resolve_embedding_model(resolved_provider, model)
    resolved_base_url = resolve_embedding_base_url(resolved_provider)
    text_list = [texts] if isinstance(texts, str) else list(texts)
    resolved_dimensions = dimensions if dimensions is not None else resolve_embedding_dimensions(resolved_provider)

    with create_httpx_client(timeout=timeout) as client:
        response = client.post(
            f"{openai_compatible_base_url(resolved_base_url)}/embeddings",
            json=_build_embedding_payload(resolved_model, texts if isinstance(texts, str) else text_list, resolved_dimensions),
            headers=openai_embedding_headers(resolved_provider),
        )
        response.raise_for_status()
        result = [item.get("embedding", []) for item in response.json().get("data", [])]
        logger.info(
            "embedding_request done provider=%s model=%s count=%d elapsed=%.2fs",
            resolved_provider,
            resolved_model,
            len(result),
            time.time() - start_ts,
        )
        return result


async def embedding_request_async(
    texts: str | list[str],
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    dimensions: Optional[int] = None,
    timeout: float | httpx.Timeout = 60.0,
) -> list[list[float]]:
    """异步 embedding 请求 - OpenAI API。"""
    start_ts = time.time()
    resolved_provider = resolve_embedding_provider(provider)
    resolved_model = resolve_embedding_model(resolved_provider, model)
    resolved_base_url = resolve_embedding_base_url(resolved_provider)
    text_list = [texts] if isinstance(texts, str) else list(texts)
    resolved_dimensions = dimensions if dimensions is not None else resolve_embedding_dimensions(resolved_provider)

    async with create_async_httpx_client(timeout=timeout) as client:
        response = await client.post(
            f"{openai_compatible_base_url(resolved_base_url)}/embeddings",
            json=_build_embedding_payload(resolved_model, texts if isinstance(texts, str) else text_list, resolved_dimensions),
            headers=openai_embedding_headers(resolved_provider),
        )
        response.raise_for_status()
        result = [item.get("embedding", []) for item in response.json().get("data", [])]
        logger.info(
            "embedding_request_async done provider=%s model=%s count=%d elapsed=%.2fs",
            resolved_provider,
            resolved_model,
            len(result),
            time.time() - start_ts,
        )
        return result
