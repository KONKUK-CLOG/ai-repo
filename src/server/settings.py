"""Application settings loaded from environment variables."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration settings."""
    
    # Server Configuration
    SERVER_API_KEY: str = "dev-api-key"
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    
    # Blog API
    BLOG_API_URL: str = "https://api.example.com/blog"
    BLOG_API_KEY: Optional[str] = None
    
    # Vector Database
    VECTOR_DB_URL: str = "http://localhost:6333"
    VECTOR_DB_COLLECTION: str = "code_embeddings"
    EMBED_BATCH_SIZE: int = 100
    
    # Graph Database
    GRAPH_DB_URL: str = "bolt://localhost:7687"
    GRAPH_DB_USER: str = "neo4j"
    GRAPH_DB_PASSWORD: Optional[str] = None
    
    # Notion
    NOTION_TOKEN: Optional[str] = None
    
    # GitHub
    GITHUB_TOKEN: Optional[str] = None
    
    # Limits
    MAX_DIFF_BYTES: int = 10485760  # 10MB
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

