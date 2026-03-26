"""Application settings loaded from environment variables."""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    # Server Configuration
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    
    
    # Blog API
    BLOG_API_URL: str = "https://api.example.com/blog"
    BLOG_API_KEY: Optional[str] = None

    JAVA_BACKEND_BASE_URL: str = "http://localhost:9001"
    JAVA_BACKEND_TIMEOUT: float = 10.0
    JAVA_BACKEND_JWKS_URL: Optional[str] = None
    JAVA_BACKEND_JWT_ALGORITHMS: str = "RS256"
    JAVA_BACKEND_JWT_AUDIENCE: Optional[str] = None
    JAVA_BACKEND_JWT_ISSUER: Optional[str] = None
    
    # Service-to-service authentication
    JAVA_BACKEND_SERVICE_JWT: Optional[str] = None
    JAVA_BACKEND_SERVICE_CLIENT_ID: Optional[str] = None
    JAVA_BACKEND_SERVICE_CLIENT_SECRET: Optional[str] = None
    JAVA_BACKEND_SERVICE_JWT_REFRESH_PATH: Optional[str] = "/api/v1/auth/service-jwt"
    JAVA_BACKEND_SERVICE_JWT_SCOPE: Optional[str] = None
    JAVA_BACKEND_SERVICE_TOKEN_SKEW_SECONDS: int = 60
    JAVA_BACKEND_SERVICE_REFRESH_MIN_INTERVAL: int = 300
    JAVA_BACKEND_SERVICE_REFRESH_BACKOFF_SECONDS: int = 5
    JAVA_BACKEND_SERVICE_REFRESH_BACKOFF_MAX_SECONDS: int = 300
    JAVA_BACKEND_SERVICE_JWT_ALGORITHMS: Optional[str] = None
    JAVA_BACKEND_SERVICE_JWT_AUDIENCE: Optional[str] = None
    JAVA_BACKEND_SERVICE_JWT_ISSUER: Optional[str] = None
    
    # Vector Database
    VECTOR_DB_URL: str = "http://localhost:6333"
    VECTOR_DB_COLLECTION: str = "code_embeddings"
    EMBED_BATCH_SIZE: int = 100
    
    # Graph Database
    GRAPH_DB_URL: str = "bolt://localhost:7687"
    GRAPH_DB_USER: str = "neo4j"
    GRAPH_DB_PASSWORD: Optional[str] = None

    # Codebase chunks in MongoDB (Lambda may use URI from env)
    CODEBASE_MONGO_URI: Optional[str] = None
    CODEBASE_MONGO_DB: str = "clog"
    CODEBASE_MONGO_COLLECTION: str = "codebase_chunks"
    CODEBASE_MONGO_USER_ID_FIELD: str = "user_id"
    CODEBASE_MONGO_PATH_FIELD: str = "path"
    CODEBASE_MONGO_CONTENT_FIELD: str = "content"
    CODEBASE_MONGO_PREVIEW_MAX_CHARS: int = 2000
    
    # GitHub OAuth (일부 라우트/테스트에서만 사용; TS↔Java 플로우에서는 생략 가능)
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: Optional[str] = None

    # LLM API Configuration
    OPENAI_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7
    
    # Feature Flags
    ENABLE_DIRECT_TOOLS: bool = False  # 개발 환경에서만 직접 툴 실행 엔드포인트 활성화
    # Lambda 등 무상태 배포: 백그라운드 스케줄러·서비스 토큰 루프 비활성화
    ENABLE_BACKGROUND_TASKS: bool = True
    
    # Limits
    MAX_DIFF_BYTES: int = 10485760  # 10MB


settings = Settings()

