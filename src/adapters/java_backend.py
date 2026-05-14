"""Async client helpers for communicating with the Java backend."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import httpx

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
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return headers


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    url = _build_url(path)
    headers = _build_headers(extra_headers=extra_headers)
    request_timeout = timeout or _default_timeout()

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
        body_preview = exc.response.text[:500]
        logger.error(
            "Java backend responded with status %s for %s %s: %s",
            exc.response.status_code,
            method,
            url,
            body_preview,
        )
        raise JavaBackendError(
            f"Java backend request failed with status {exc.response.status_code}"
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Java backend request failed for %s %s: %s", method, url, exc)
        raise JavaBackendError("Java backend request failed") from exc

    if not response.content:
        return {}

    try:
        return response.json()
    except json.JSONDecodeError as exc:
        preview = response.text[:200]
        logger.error("Failed to decode Java backend JSON response from %s: %s", url, preview)
        raise JavaBackendError("Invalid JSON response from Java backend") from exc


async def get_user_blog_posts(
    user_id: int,
    limit: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    """Fetch user's blog posts from the Java backend (GET /api/v1/blog/posts)."""
    path = f"/api/v1/blog/posts?user_id={user_id}&limit={limit}&offset={offset}"
    return await _request("GET", path)
