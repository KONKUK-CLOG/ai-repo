"""Dependency injection for FastAPI routes.

FastAPI 라우트에서 사용하는 의존성 주입 함수들입니다.
공유 API 키 기반의 사용자 인증을 처리합니다.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import Header, HTTPException, status

from src.models.user import User
from src.repositories.user_repo import user_repo

logger = logging.getLogger(__name__)


async def get_current_user(
    x_api_key: str = Header(..., alias="x-api-key", description="User API key"),
) -> User:
    """API 키로 현재 사용자를 조회합니다.

    Args:
        x_api_key: 요청 헤더의 사용자 API 키

    Returns:
        인증된 User 객체

    Raises:
        HTTPException: 401 - API 키가 유효하지 않음
    """
    try:
        user = await user_repo.get_by_api_key(x_api_key)
    except httpx.HTTPError as exc:
        logger.error("Failed to fetch user from Java backend: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch user information from backend",
        ) from exc

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    return user
