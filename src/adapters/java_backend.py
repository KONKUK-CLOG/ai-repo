"""Async client helpers for communicating with the Java backend."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

import httpx

from src.server.settings import settings

logger = logging.getLogger(__name__)

# 사용자별 서버 간 통신용 JWT 캐시
_user_service_jwt_cache: Dict[int, str] = {}


def get_cached_service_jwt(user_id: int) -> Optional[str]:
    """캐시된 서비스 JWT를 가져옵니다.
    
    Args:
        user_id: 사용자 ID (GitHub user_id 또는 Java 백엔드의 내부 사용자 ID)
    
    Returns:
        캐시된 JWT 토큰 문자열, 없으면 None
    """
    return _user_service_jwt_cache.get(user_id)


def set_service_jwt(user_id: int, jwt: str) -> None:
    """서비스 JWT를 캐시에 저장합니다.
    
    Args:
        user_id: 사용자 ID
        jwt: JWT 토큰 문자열
    """
    _user_service_jwt_cache[user_id] = jwt
    logger.debug(f"Cached service JWT for user {user_id}")


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
    use_service_token: bool = False,
    user_id: Optional[int] = None,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}

    if extra_headers:
        headers.update(extra_headers)

    token: Optional[str] = None
    if bearer_token:
        token = bearer_token
    elif use_service_token:
        # user_id가 있으면 해당 사용자의 캐시된 JWT 사용, 없으면 기본 서비스 JWT
        if user_id:
            token = get_cached_service_jwt(user_id)
            if not token:
                logger.warning(
                    f"No cached JWT for user {user_id}, using default service JWT"
                )
                token = settings.JAVA_BACKEND_SERVICE_JWT
        else:
            token = settings.JAVA_BACKEND_SERVICE_JWT
        
        if not token:
            raise JavaBackendError("JAVA_BACKEND_SERVICE_JWT is not configured.")

    if token:
        headers.setdefault("Authorization", f"Bearer {token}")

    return headers


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    bearer_token: Optional[str] = None,
    use_service_token: bool = False,
    user_id: Optional[int] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    url = _build_url(path)
    headers = _build_headers(
        bearer_token=bearer_token,
        use_service_token=use_service_token,
        user_id=user_id,
        extra_headers=extra_headers,
    )

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


async def sync_github_user(github_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Send GitHub user profile data to the Java backend and receive an API key payload."""
    return await _request(
        "POST",
        "/api/v1/users/github",
        json_body=github_profile,
        use_service_token=True,
    )


async def get_service_jwt_for_user(user_id: int) -> str:
    """Java 서버에서 user_id에 대한 서버 간 통신용 JWT를 발급받습니다.
    
    Args:
        user_id: 사용자 ID (GitHub user_id 또는 Java 백엔드의 내부 사용자 ID)
    
    Returns:
        서버 간 통신용 JWT 토큰 문자열
    
    Raises:
        JavaBackendError: Java 서버 요청 실패 또는 JWT가 응답에 없음
    """
    payload = await _request(
        "POST",
        f"/api/v1/users/{user_id}/service-jwt",
        json_body={"user_id": user_id},
        use_service_token=True,
    )
    
    # 다양한 가능한 필드명 시도
    jwt_token = (
        payload.get("jwt")
        or payload.get("token")
        or payload.get("service_jwt")
        or payload.get("access_token")
    )
    
    if not jwt_token:
        raise JavaBackendError(
            f"Java backend response missing JWT token. Response: {payload}"
        )
    
    logger.info(f"Service JWT issued for user {user_id}")
    return jwt_token


async def get_user_by_id(user_id: int) -> Dict[str, Any]:
    """Fetch a user record by numeric ID using the service JWT."""
    return await _request(
        "GET",
        f"/api/v1/users/{user_id}",
        use_service_token=True,
    )


async def get_user_by_api_key(api_key: str) -> Dict[str, Any]:
    """Resolve a user using their API key."""
    return await _request(
        "GET",
        f"/api/v1/users/by-api-key/{api_key}",
        use_service_token=True,
    )


async def create_blog_post(api_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new blog post via the Java backend on behalf of the API key owner."""
    return await _request(
        "POST",
        "/api/v1/blog/posts",
        use_service_token=True,
        json_body=payload,
        extra_headers={"X-User-Api-Key": api_key},
    )

