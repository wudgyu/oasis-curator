"""
应用配置

通过环境变量覆盖默认值，开发环境使用 .env 文件
"""

from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "Oasis Curator"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # JWT
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 小时

    # 数据库
    DATABASE_URL: str = "sqlite:///ai_platform.db"

    # ========== LLM 配置 ==========
    # DeepSeek
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # Kimi (Moonshot)
    KIMI_API_KEY: Optional[str] = None
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL: str = "moonshot-v1-8k"

    # Ark (火山方舟)
    ARK_API_KEY: Optional[str] = None
    ARK_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"
    ARK_MODEL: str = "deepseek-v3-250324"

    # 默认 provider 与降级链
    LLM_DEFAULT_PROVIDER: str = "deepseek"
    LLM_FALLBACK_PROVIDERS: str = "kimi,ark"

    # 请求参数
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_BASE_DELAY: float = 1.0
    LLM_RETRY_BACKOFF: float = 2.0
    LLM_REQUEST_TIMEOUT: int = 60

    # ========== Embedding 配置 ==========
    # 向量化模型选择（auto 优先级：智谱 embedding-2 > Ollama bge-m3 > 本地 MiniLM）
    EMBEDDING_PROVIDER: str = "auto"
    ZHIPU_API_KEY: Optional[str] = None
    ZHIPU_EMBEDDING_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    ZHIPU_EMBEDDING_MODEL: str = "embedding-2"
    OLLAMA_HOST: str = "http://localhost:11434"
    OLLAMA_EMBED_MODEL: str = "bge-m3"

    # ========== 向量数据库（ChromaDB） ==========
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 18000
    CHROMA_TENANT: str = "curator"  # 项目命名空间
    CHROMA_DATABASE: str = "oasis"  # 向量库

    # ========== 文档上传 ==========
    UPLOAD_DIR: str = "./data/uploads"  # 上传文档的落盘目录（相对 backend 运行目录）

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()