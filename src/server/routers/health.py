"""Health check endpoints."""
from fastapi import APIRouter
from typing import Dict, Any
from src.server.settings import settings

router = APIRouter()


@router.get("/healthz")
async def health_check() -> Dict[str, str]:
    """Basic health check endpoint.
    
    Returns:
        Simple status response
    """
    return {"status": "ok"}


@router.get("/readyz")
async def readiness_check() -> Dict[str, Any]:
    """Readiness check endpoint.
    
    Checks if required environment variables are set.
    
    Returns:
        Status response with readiness info
    """
    # Check if critical environment variables are present
    checks = {
        "blog_api_url": bool(settings.BLOG_API_URL),
        "vector_db_url": bool(settings.VECTOR_DB_URL),
        "graph_db_url": bool(settings.GRAPH_DB_URL),
    }
    
    ready = all(checks.values())
    
    return {
        "status": "ok" if ready else "not_ready",
        "checks": checks
    }

