"""
出站网络环境初始化。

默认保留环境代理，并通过 NO_PROXY 精细控制直连域名。
"""
from __future__ import annotations

import os
from typing import Iterable
from urllib.parse import urlparse

import httpx

PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "GRPC_PROXY",
    "grpc_proxy",
)

NO_PROXY_ENV_KEYS = (
    "NO_PROXY",
    "no_proxy",
    "NO_GRPC_PROXY",
    "no_grpc_proxy",
)

DEFAULT_DIRECT_HOSTS = (
    "localhost",
    "127.0.0.1",
    "::1",
    "mineru.net",
    "openxlab.org.cn",
)


def _split_csv(value: str | Iterable[str] | None) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = value.split(",")
    else:
        items = list(value)
    return [str(item).strip() for item in items if str(item).strip()]


def _extract_host(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    if raw == "::1":
        return raw

    if "://" in raw:
        parsed = urlparse(raw)
    else:
        parsed = urlparse(f"//{raw}")

    host = parsed.hostname or raw.split("/", 1)[0].split(":", 1)[0]
    normalized = host.strip().lower().lstrip(".")
    return normalized or None


def build_direct_hosts(
    *values: str,
    extra_hosts: str = "",
) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()

    for candidate in (*DEFAULT_DIRECT_HOSTS, *values, *_split_csv(extra_hosts)):
        host = _extract_host(candidate)
        if not host or host in seen:
            continue
        seen.add(host)
        hosts.append(host)

    return hosts


def _merge_no_proxy_hosts(hosts: Iterable[str]) -> str:
    merged: list[str] = []
    seen: set[str] = set()

    for env_key in NO_PROXY_ENV_KEYS:
        for item in _split_csv(os.environ.get(env_key)):
            host = _extract_host(item) or item.strip().lower()
            if not host or host in seen:
                continue
            seen.add(host)
            merged.append(host)

    for item in hosts:
        host = _extract_host(item)
        if not host or host in seen:
            continue
        seen.add(host)
        merged.append(host)

    return ",".join(merged)


def configure_network_environment(
    *,
    proxy_mode: str = "env",
    direct_hosts: Iterable[str] = (),
) -> dict[str, object]:
    normalized_mode = (proxy_mode or "direct").strip().lower()
    direct_mode = normalized_mode in {"direct", "off", "disabled", "bypass"}
    resolved_mode = "direct" if direct_mode else "env"
    os.environ["AI_WRITER_OUTBOUND_PROXY_MODE"] = resolved_mode

    cleared_proxy_keys: list[str] = []
    if direct_mode:
        for env_key in PROXY_ENV_KEYS:
            if os.environ.pop(env_key, None) is not None:
                cleared_proxy_keys.append(env_key)

    merged_no_proxy = _merge_no_proxy_hosts(direct_hosts)
    if merged_no_proxy:
        for env_key in NO_PROXY_ENV_KEYS:
            os.environ[env_key] = merged_no_proxy

    return {
        "proxy_mode": resolved_mode,
        "cleared_proxy_keys": cleared_proxy_keys,
        "no_proxy": merged_no_proxy,
    }


def create_httpx_client(*args, **kwargs) -> httpx.Client:
    kwargs.setdefault("trust_env", os.environ.get("AI_WRITER_OUTBOUND_PROXY_MODE") == "env")
    return httpx.Client(*args, **kwargs)


def create_async_httpx_client(*args, **kwargs) -> httpx.AsyncClient:
    kwargs.setdefault("trust_env", os.environ.get("AI_WRITER_OUTBOUND_PROXY_MODE") == "env")
    return httpx.AsyncClient(*args, **kwargs)
