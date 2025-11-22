"""Async client helpers for communicating with the Java backend."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from src.server.settings import settings

logger = logging.getLogger(__name__)

# 주석 처리: 서비스 간 JWT 통신 시 사용했던 함수들. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
# Java 서버와 Python 서버가 같은 EC2에 배포되므로 보안이 필요하지 않음
# 서비스 간 통신용 JWT 캐시
# _service_jwt: Optional[str] = None
# _service_jwt_expires_at: Optional[int] = None


# def cache_service_jwt(jwt: str, expires_at: Optional[int] = None) -> None:
#     """서비스 간 통신용 JWT를 캐시에 저장합니다.
#     
#     주석 처리: 서비스 간 JWT 캐싱 함수. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
#     """
#     global _service_jwt, _service_jwt_expires_at
#     _service_jwt = jwt
#     _service_jwt_expires_at = expires_at
#     logger.debug("Cached service JWT (expires_at=%s)", expires_at)


# def get_cached_service_jwt() -> Optional[str]:
#     """캐시된 서비스 JWT를 반환합니다.
#     
#     주석 처리: 캐시된 JWT 조회 함수. 현재 사용하지 않음
#     """
#     if _service_jwt and not _service_jwt_expired():
#         return _service_jwt
#     return None


# def _service_jwt_expired(buffer_seconds: int = 60) -> bool:
#     """JWT 만료 확인 함수. 현재 사용하지 않음"""
#     if _service_jwt is None:
#         return True
#     if _service_jwt_expires_at is None:
#         return False
#     current_time = int(time.time())
#     return current_time >= (_service_jwt_expires_at - buffer_seconds)


# async def refresh_service_jwt(payload: Optional[Dict[str, Any]] = None) -> str:
#     """Java 서버에 요청하여 새로운 서비스 JWT를 발급받습니다.
#     
#     주석 처리: JWT 갱신 함수. 현재 사용하지 않음
#     
#     Args:
#         payload: 발급 요청 시 함께 보낼 JSON 본문 (선택)
# 
#     Returns:
#         새로 발급받은 JWT 문자열
# 
#     Raises:
#         JavaBackendError: 발급 요청 실패
#     """
#     refresh_path = settings.JAVA_BACKEND_SERVICE_JWT_REFRESH_PATH or "/api/v1/auth/service-jwt"
#     response = await _request(
#         "POST",
#         refresh_path,
#         json_body=payload,
#     )
# 
#     jwt_token = response.get("jwt") or response.get("token") or response.get("access_token")
#     if not jwt_token:
#         raise JavaBackendError("Service JWT response missing token")
# 
#     expires_at = response.get("expires_at") or response.get("exp")
#     expires_at_int: Optional[int] = None
#     if isinstance(expires_at, (int, float)):
#         expires_at_int = int(expires_at)
# 
#     cache_service_jwt(jwt_token, expires_at_int)
#     return jwt_token


# async def ensure_service_jwt(force_refresh: bool = False) -> str:
#     """서비스 JWT를 확보합니다. 필요 시 발급 엔드포인트를 호출합니다.
#     
#     주석 처리: JWT 확보 함수. 현재 사용하지 않음
#     """
#     if not force_refresh:
#         cached = get_cached_service_jwt()
#         if cached:
#             return cached
# 
#     # 환경 변수 기반 기본 토큰
#     if settings.JAVA_BACKEND_SERVICE_JWT and not force_refresh:
#         cache_service_jwt(settings.JAVA_BACKEND_SERVICE_JWT)
#         return settings.JAVA_BACKEND_SERVICE_JWT
# 
#     return await refresh_service_jwt()
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
    """HTTP 요청 헤더를 구성합니다.
    
    주석 처리: bearer_token 관련 로직은 유지하되, 현재는 같은 EC2 내부 통신이므로 JWT 불필요
    """
    headers: Dict[str, str] = {"Accept": "application/json"}

    if extra_headers:
        headers.update(extra_headers)

    # 주석 처리: 서비스 간 JWT 통신 시 사용했던 로직. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
    # if bearer_token:
    #     headers.setdefault("Authorization", f"Bearer {bearer_token}")

    return headers


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[Dict[str, Any]] = None,
    bearer_token: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: Optional[float] = None,
) -> Dict[str, Any]:
    url = _build_url(path)
    headers = _build_headers(
        bearer_token=bearer_token,
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


async def get_user_by_id(
    user_id: int,
    bearer_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch a user record by numeric ID using the provided JWT token.
    
    주석 처리: 현재는 사용하지 않지만, 필요시에만 사용할 수 있도록 유지
    
    Args:
        user_id: 사용자 ID
        bearer_token: Java 서버로 전달할 JWT 토큰 (현재는 사용하지 않음)
    """
    # 주석 처리: 서비스 JWT 확보 로직. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
    # if bearer_token is None:
    #     bearer_token = await ensure_service_jwt()
    
    return await _request(
        "GET",
        f"/api/v1/users/{user_id}",
        bearer_token=None,  # JWT 없이 요청 (같은 EC2 내부 통신)
    )


async def create_blog_post(api_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new blog post via the Java backend on behalf of the API key owner."""
    return await _request(
        "POST",
        "/api/v1/blog/posts",
        json_body=payload,
        extra_headers={"X-User-Api-Key": api_key},
    )

