"""Health check endpoints."""
from typing import Any, Dict

from fastapi import APIRouter

from src.server.settings import settings

router = APIRouter()


@router.get("/healthz")
async def health_check() -> Dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readiness_check() -> Dict[str, Any]:
    """Readiness for LLM + Mongo codebase search + Java blog API."""
    checks = {
        "openai_api_key": bool(settings.OPENAI_API_KEY),
        "codebase_mongo_uri": bool(settings.CODEBASE_MONGO_URI),
        "java_backend_base_url": bool(settings.JAVA_BACKEND_BASE_URL),
    }
    ready = all(checks.values())
    return {
        "status": "ok" if ready else "not_ready",
        "checks": checks,
    }
