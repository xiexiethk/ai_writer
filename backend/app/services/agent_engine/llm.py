"""
Agent RAG Engine - LLM 包装
统一使用在线聊天模型。
"""
import logging
from typing import Any, Optional

from app.services.llm_gateway import (
    DEEPSEEK_PROVIDER,
    resolve_chat_base_url,
    resolve_chat_provider,
    resolve_chat_model,
    resolve_chat_api_key,
    resolve_chat_thinking,
)

logger = logging.getLogger(__name__)


def create_chat_llm(
    model: Optional[str] = None,
    provider: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.7,
    **kwargs
) -> Any:
    """
    创建 LangChain LLM 实例。
    
    Args:
        model: 模型名称
        provider: 模型提供方
        base_url: 服务地址
        temperature: 温度参数
        **kwargs: 其他参数传递给底层 LLM
    
    Returns:
        ChatOpenAI 实例
    """
    resolved_provider = resolve_chat_provider(provider)
    resolved_model = resolve_chat_model(resolved_provider, model)
    resolved_base_url = (base_url or resolve_chat_base_url(resolved_provider)).rstrip("/")

    try:
        from langchain_openai import ChatOpenAI

        extra_kwargs = {"extra_body": {"chat_template_kwargs": {"thinking": False}}}
        thinking = resolve_chat_thinking(resolved_provider)
        if resolved_provider == DEEPSEEK_PROVIDER and thinking:
            extra_kwargs["extra_body"] = {"thinking": thinking}

        llm = ChatOpenAI(
            model=resolved_model,
            base_url=resolved_base_url,
            api_key=resolve_chat_api_key(resolved_provider),
            temperature=temperature,
            **extra_kwargs,
            **kwargs
        )
        logger.info("创建 %s LLM 实例: %s @ %s", resolved_provider, resolved_model, resolved_base_url)
        return llm
    except Exception as e:
        logger.error(f"创建 LLM 失败: {e}")
        raise
