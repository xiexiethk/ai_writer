"""
应用配置
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import List, Optional
import json
import os

from app.core.network import build_direct_hosts, configure_network_environment


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PRIMARY_ENV_FILE = BACKEND_ROOT / ".env"
FALLBACK_ENV_FILE = BACKEND_ROOT / ".env.example"


def _resolve_path(value: str, default_subdir: str) -> str:
    raw_value = (value or '').strip()
    candidate = Path(raw_value) if raw_value else BACKEND_ROOT / default_subdir
    if not candidate.is_absolute():
        candidate = (BACKEND_ROOT / candidate).resolve()
    candidate.mkdir(parents=True, exist_ok=True)
    return str(candidate)


class Settings(BaseSettings):
    """应用配置类"""

    # 应用信息
    APP_NAME: str = "AI Writer Backend"
    APP_VERSION: str = "0.0.1"
    DEBUG: bool = True

    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 28000

    # CORS 配置
    CORS_ORIGINS: List[str] = ["*"]

    # 文件存储配置
    UPLOAD_DIR: str = "./uploads"
    PARSE_OUTPUT_DIR: str = "./parsed_data"
    MAX_UPLOAD_SIZE: int = 104857600  # 100MB

    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./ai_writer.db"

    # Milvus 配置（可切换 Zilliz Cloud）
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19531
    MILVUS_URI: str = "http://localhost:19531"
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # 安全配置
    SECRET_KEY: str = "ai_writer_secret_key_change_me_in_prod"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天

    # MinerU API 配置（在线 API）
    MINERU_API_TOKEN: str = ""
    MINERU_BACKEND: str = "api"
    MINERU_OUTPUT_DIR: str = "./parsed_output"
    MINERU_LANG: str = "ch"

    # 批量任务配置
    BATCH_VECTORIZE_MAX_CONCURRENCY: int = 4
    SKIP_EMBEDDING_WARMUP: bool = False

    # 模型服务配置
    MODEL_PROVIDER: str = "deepseek"
    CHAT_MODEL_PROVIDER: Optional[str] = None
    EMBEDDING_MODEL_PROVIDER: Optional[str] = None

    # DeepSeek 配置（聊天 API）
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_CHAT_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_CHAT_MODEL: str = "deepseek-v4-flash"
    DEEPSEEK_THINKING_TYPE: str = "disabled"
    DEEPSEEK_EMBEDDING_MODEL: Optional[str] = None

    # OpenAI 配置（Embedding API）
    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_BASE_URL: str = "https://api.openai.com"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536

    # Embedding 通用配置（覆盖 OpenAI 嵌入配置）
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = ""
    EMBEDDING_MODEL: str = ""
    EMBEDDING_DIMENSIONS: int = 0

    # 出站网络配置
    OUTBOUND_PROXY_MODE: str = "env"
    NO_PROXY_EXTRA: str = ""

    class Config:
        env_file = str(PRIMARY_ENV_FILE if PRIMARY_ENV_FILE.exists() else FALLBACK_ENV_FILE)
        env_file_encoding = "utf-8"

    @property
    def CORS_ORIGINS_list(self) -> List[str]:
        """解析 CORS_ORIGINS"""
        if isinstance(self.CORS_ORIGINS, str):
            try:
                return json.loads(self.CORS_ORIGINS)
            except json.JSONDecodeError:
                return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return self.CORS_ORIGINS


settings = Settings()
settings.UPLOAD_DIR = _resolve_path(settings.UPLOAD_DIR, "uploads")
settings.PARSE_OUTPUT_DIR = _resolve_path(settings.PARSE_OUTPUT_DIR, "parsed_output")
settings.MINERU_OUTPUT_DIR = _resolve_path(settings.MINERU_OUTPUT_DIR, "parsed_output")

database_url = settings.DATABASE_URL
sqlite_prefix = "sqlite+aiosqlite:///"
if database_url.startswith(sqlite_prefix):
    sqlite_path = database_url[len(sqlite_prefix):]
    if sqlite_path.startswith("./"):
        resolved_db = (BACKEND_ROOT / sqlite_path[2:]).resolve()
        resolved_db.parent.mkdir(parents=True, exist_ok=True)
        settings.DATABASE_URL = f"{sqlite_prefix}{resolved_db}"

configure_network_environment(
    proxy_mode=settings.OUTBOUND_PROXY_MODE,
    direct_hosts=build_direct_hosts(
        settings.DEEPSEEK_CHAT_BASE_URL,
        settings.OPENAI_EMBEDDING_BASE_URL,
        settings.EMBEDDING_BASE_URL,
        extra_hosts=settings.NO_PROXY_EXTRA,
    ),
)
