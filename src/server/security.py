"""Security utilities for verifying Java backend JWTs."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import jwt
from jwt import InvalidTokenError, PyJWKClient

from src.server.settings import settings

logger = logging.getLogger(__name__)

_jwks_client: Optional[PyJWKClient] = None
_jwks_client_url: Optional[str] = None


class JWTVerificationError(Exception):
    """Raised when a JWT cannot be verified."""


def _resolve_jwks_url() -> str:
    if settings.JAVA_BACKEND_JWKS_URL:
        return settings.JAVA_BACKEND_JWKS_URL
    base = settings.JAVA_BACKEND_BASE_URL.rstrip("/")
    return f"{base}/.well-known/jwks.json"


def _get_algorithms() -> List[str]:
    algorithms = [
        alg.strip()
        for alg in settings.JAVA_BACKEND_JWT_ALGORITHMS.split(",")
        if alg.strip()
    ]
    return algorithms or ["RS256"]


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client, _jwks_client_url
    url = _resolve_jwks_url()
    if _jwks_client is None or _jwks_client_url != url:
        logger.info("Initializing PyJWKClient for JWKS URL: %s", url)
        _jwks_client = PyJWKClient(url)
        _jwks_client_url = url
    return _jwks_client


async def verify_jwt(token: str) -> Dict[str, Any]:
    """Verify a JWT issued by the Java backend and return its payload."""
    client = _get_jwks_client()

    try:
        signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
        decoded = jwt.decode(
            token,
            signing_key.key,
            algorithms=_get_algorithms(),
            audience=settings.JAVA_BACKEND_JWT_AUDIENCE,
            issuer=settings.JAVA_BACKEND_JWT_ISSUER,
            options={
                "verify_aud": settings.JAVA_BACKEND_JWT_AUDIENCE is not None,
                "verify_iss": settings.JAVA_BACKEND_JWT_ISSUER is not None,
            },
        )
        return decoded
    except InvalidTokenError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise JWTVerificationError(str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected error verifying JWT: %s", exc)
        raise JWTVerificationError("Failed to verify JWT") from exc

