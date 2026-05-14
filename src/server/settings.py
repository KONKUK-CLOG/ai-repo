"""Application settings loaded from environment variables."""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Minimal settings for Lambda LLM bridge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000

    JAVA_BACKEND_BASE_URL: str = "http://localhost:9001"
    JAVA_BACKEND_TIMEOUT: float = 10.0

    CODEBASE_MONGO_URI: Optional[str] = None
    CODEBASE_MONGO_DB: str = "clog"
    CODEBASE_MONGO_COLLECTION: str = "codebase_chunks"
    CODEBASE_MONGO_USER_ID_FIELD: str = "user_id"
    CODEBASE_MONGO_PATH_FIELD: str = "path"
    CODEBASE_MONGO_CONTENT_FIELD: str = "content"
    CODEBASE_MONGO_PREVIEW_MAX_CHARS: int = 2000

    OPENAI_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7


settings = Settings()
