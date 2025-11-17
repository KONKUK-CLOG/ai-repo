"""Application settings loaded from environment variables."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration settings."""
    
    # Server Configuration
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    
    # GitHub OAuth (다중 사용자 인증)
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/auth/github/callback"
    
    # GitHub (기존 - git 작업용)
    GITHUB_TOKEN: Optional[str] = None
    
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
    
    # LLM API Configuration
    OPENAI_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gpt-4-turbo-preview"
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.7
    
    # Feature Flags
    ENABLE_DIRECT_TOOLS: bool = False  # 개발 환경에서만 직접 툴 실행 엔드포인트 활성화
    
    # Limits
    MAX_DIFF_BYTES: int = 10485760  # 10MB
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

