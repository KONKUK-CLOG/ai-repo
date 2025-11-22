"""Dependency injection for FastAPI routes.

주석 처리: 이전에는 JWT 기반의 사용자 인증을 처리했으나,
현재는 Java 서버를 통해 내부 통신하므로 JWT 검증이 불필요합니다.
Java 서버에서 이미 인증을 완료했고, 요청 본문에 user_id를 포함하여 전달합니다.

주석 처리된 함수들은 TS 직접 통신 시 사용했던 함수들입니다.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

# 주석 처리: 주석 처리된 함수에서 참조하므로 import는 유지 (주석 처리된 코드 이해를 위해)
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.models.user import User
from src.repositories.user_repo import user_repo
# 주석 처리: JWT 검증 함수들. 현재는 사용하지 않음
# from src.server.security import (
#     verify_jwt,
#     verify_service_jwt,
#     JWTVerificationError,
# )

logger = logging.getLogger(__name__)

# 주석 처리: HTTP Bearer 토큰 스키마. 현재는 사용하지 않음
# security = HTTPBearer()
# service_security = HTTPBearer(description="Service-to-service JWT")


# 주석 처리: TS 직접 통신 시 사용했던 함수. 현재는 Java 서버를 통해 내부 통신하므로 사용하지 않음
# Java 서버에서 이미 인증을 완료했고, 요청 본문에 user_id를 포함하여 전달하므로 JWT 검증이 불필요함
# async def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Depends(security),
# ) -> User:
#     """JWT로 현재 사용자를 인증하고 조회합니다.
# 
#     Args:
#         credentials: Authorization 헤더의 Bearer 토큰
# 
#     Returns:
#         인증된 User 객체
# 
#     Raises:
#         HTTPException: 
#             - 401 - JWT가 유효하지 않음
#             - 403 - 사용자를 찾을 수 없음
#             - 502 - Java 백엔드 요청 실패
#     """
#     token = credentials.credentials
#     
#     try:
#         # JWT 검증 (JWKS로 공개키 검증)
#         payload = await verify_jwt(token)
#     except JWTVerificationError as exc:
#         logger.warning("JWT verification failed: %s", exc)
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid or expired token",
#             headers={"WWW-Authenticate": "Bearer"},
#         ) from exc
#     
#     # JWT payload에서 사용자 ID 추출
#     # Java 서버가 발급한 JWT의 user_id 필드 사용
#     user_id = payload.get("user_id")
#     
#     if not user_id:
#         logger.error("JWT payload missing user identifier: %s", payload)
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Token missing user identifier",
#         )
#     
#     # 사용자 ID로 사용자 정보 조회
#     # Java 서버에 요청할 때는 받은 JWT를 그대로 전달
#     try:
#         user = await user_repo.get_by_id(user_id, bearer_token=token)
#     except Exception as exc:
#         logger.error("Failed to fetch user from Java backend: %s", exc)
#         raise HTTPException(
#             status_code=status.HTTP_502_BAD_GATEWAY,
#             detail="Failed to fetch user information from backend",
#         ) from exc
#     
#     if not user:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="User not found",
#         )
#     
#     return user


# 주석 처리: 서비스 간 JWT 통신 시 사용했던 함수. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
# Java 서버에서 Python 서버로의 요청은 같은 EC2 내부 통신이므로 별도 인증이 필요하지 않음
# async def get_java_service_identity(
#     credentials: HTTPAuthorizationCredentials = Depends(service_security),
# ) -> Dict[str, Any]:
#     """Verify service-to-service JWTs issued to the Java backend.
#     
#     주석 처리: 서비스 간 JWT 통신 시 사용했던 함수. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
#     """
#     token = credentials.credentials
# 
#     try:
#         payload = await verify_service_jwt(token)
#     except JWTVerificationError as exc:
#         logger.warning("Service JWT verification failed: %s", exc)
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Invalid service token",
#             headers={"WWW-Authenticate": "Bearer"},
#         ) from exc
# 
#     return payload
