"""
Agent RAG Engine package.

避免在包导入时构建 service 单例，降低外部依赖未就绪时的副作用。
需要 service 时请从 `app.services.agent_engine.service` 显式导入。
"""

__all__ = []
