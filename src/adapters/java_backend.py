"""Async client helpers for communicating with the Java backend."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import httpx

from src.adapters.service_token_manager import (
    ServiceTokenError,
    service_token_manager,
)
from src.server.settings import settings

logger = logging.getLogger(__name__)
class JavaBackendError(RuntimeError):
    """Raised when the Java backend returns an unexpected response."""


def _build_url(path: str) -> str:
    if not settings.JAVA_BACKEND_BASE_URL:
        raise JavaBackendError("JAVA_BACKEND_BASE_URL is not configured.")
    base = settings.JAVA_BACKEND_BASE_URL.rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _default_timeout() -> float:
    return settings.JAVA_BACKEND_TIMEOUT or 10.0


def _build_headers(
    *,
    bearer_token: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}

    if extra_headers:
        headers.update(extra_headers)

    if bearer_token:
        headers.setdefault("Authorization", f"Bearer {bearer_token}")

    return headers


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    bearer_token: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
    service_auth: bool = False,
    retry_on_unauthorized: bool = True,
) -> Dict[str, Any]:
    url = _build_url(path)
    token = bearer_token
    attempts = 0

    async def _resolve_service_token(force: bool = False) -> str:
        try:
            return await service_token_manager.get_token(force_refresh=force)
        except ServiceTokenError as exc:
            raise JavaBackendError(str(exc)) from exc

    if service_auth and token is None:
        token = await _resolve_service_token()

    request_timeout = timeout or _default_timeout()

    while True:
        headers = _build_headers(
            bearer_token=token,
            extra_headers=extra_headers,
        )

        try:
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                response = await client.request(
                    method,
                    url,
                    json=json_body,
                    headers=headers,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            body_preview = exc.response.text[:500]
            logger.error(
                "Java backend responded with status %s for %s %s: %s",
                status_code,
                method,
                url,
                body_preview,
            )

            if (
                service_auth
                and retry_on_unauthorized
                and status_code == 401
                and attempts == 0
            ):
                attempts += 1
                logger.warning("Service JWT rejected with 401; refreshing and retrying once.")
                await service_token_manager.invalidate()
                token = await _resolve_service_token(force=True)
                continue

            raise JavaBackendError(
                f"Java backend request failed with status {status_code}"
            ) from exc
        except httpx.HTTPError as exc:
            logger.error("Java backend request failed for %s %s: %s", method, url, exc)
            raise JavaBackendError("Java backend request failed") from exc
        else:
            break

    if not response.content:
        return {}

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        preview = response.text[:200]
        logger.error("Failed to decode Java backend JSON response from %s: %s", url, preview)
        raise JavaBackendError("Invalid JSON response from Java backend") from exc


async def get_user_by_id(
    user_id: int,
    bearer_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a user record by numeric ID using the provided JWT token.
    
    Args:
        user_id: 사용자 ID
        bearer_token: Java 서버로 전달할 JWT 토큰 (없으면 서비스 JWT 사용)
    """
    return await _request(
        "GET",
        f"/api/v1/users/{user_id}",
        bearer_token=bearer_token,
        service_auth=bearer_token is None,
    )


async def create_blog_post(api_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new blog post via the Java backend on behalf of the API key owner."""
    return await _request(
        "POST",
        "/api/v1/blog/posts",
        json_body=payload,
        extra_headers={"X-User-Api-Key": api_key},
        service_auth=True,
    )

