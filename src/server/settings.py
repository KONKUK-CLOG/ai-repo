"""Application settings loaded from environment variables."""
from typing import Literal, Optional

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
    # Regex-matched candidates are BM25-ranked in Python; cap avoids huge memory use.
    CODEBASE_MONGO_BM25_MAX_CANDIDATES: int = 500
    # flat: one chunk per document (user_id + path + content). nested_user_doc: one document per user with projects[projectId].codebase[].
    CODEBASE_MONGO_LAYOUT: Literal["flat", "nested_user_doc"] = "flat"
    CODEBASE_MONGO_PROJECTS_FIELD: str = "projects"
    CODEBASE_MONGO_CODEBASE_ARRAY_FIELD: str = "codebase"

    OPENAI_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7


settings = Settings()
