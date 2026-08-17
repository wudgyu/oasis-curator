"""
应用配置

通过环境变量覆盖默认值，开发环境使用 .env 文件
"""

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()