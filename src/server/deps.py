"""Dependency injection for FastAPI routes.

FastAPI 라우트에서 사용하는 의존성 주입 함수들입니다.
JWT 기반의 사용자 인증을 처리합니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.models.user import User
from src.repositories.user_repo import user_repo
from src.server.security import (
    verify_jwt,
    verify_service_jwt,
    JWTVerificationError,
)

logger = logging.getLogger(__name__)

# HTTP Bearer 토큰 스키마
security = HTTPBearer()
service_security = HTTPBearer(description="Service-to-service JWT")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """JWT로 현재 사용자를 인증하고 조회합니다.

    Args:
        credentials: Authorization 헤더의 Bearer 토큰

    Returns:
        인증된 User 객체

    Raises:
        HTTPException: 
            - 401 - JWT가 유효하지 않음
            - 403 - 사용자를 찾을 수 없음
            - 502 - Java 백엔드 요청 실패
    """
    token = credentials.credentials
    
    try:
        # JWT 검증 (JWKS로 공개키 검증)
        payload = await verify_jwt(token)
    except JWTVerificationError as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    
    # JWT payload에서 사용자 ID 추출
    # Java 서버가 발급한 JWT의 user_id 필드 사용
    user_id = payload.get("user_id")
    
    if not user_id:
        logger.error("JWT payload missing user identifier: %s", payload)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing user identifier",
        )
    
    # 사용자 ID로 사용자 정보 조회
    # Java 서버에 요청할 때는 받은 JWT를 그대로 전달
    try:
        user = await user_repo.get_by_id(user_id, bearer_token=token)
    except Exception as exc:
        logger.error("Failed to fetch user from Java backend: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch user information from backend",
        ) from exc
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not found",
        )
    
    return user


async def get_java_service_identity(
    credentials: HTTPAuthorizationCredentials = Depends(service_security),
) -> Dict[str, Any]:
    """Verify service-to-service JWTs issued to the Java backend."""
    token = credentials.credentials

    try:
        payload = await verify_service_jwt(token)
    except JWTVerificationError as exc:
        logger.warning("Service JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid service token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return payload
