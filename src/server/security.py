"""Security utilities for verifying Java backend JWTs.

주석 처리: TS 직접 통신 시 사용했던 JWT 검증 함수들. 
현재는 Java 서버를 통해 내부 통신하므로 JWT 검증이 불필요함.
향후 필요할 수 있으므로 주석 처리하여 유지합니다.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import jwt
from jwt import InvalidTokenError, PyJWKClient

from src.server.settings import settings

logger = logging.getLogger(__name__)

# 주석 처리: JWT 검증 관련 클라이언트. 현재는 사용하지 않음
# _jwks_client: Optional[PyJWKClient] = None
# _jwks_client_url: Optional[str] = None


class JWTVerificationError(Exception):
    """Raised when a JWT cannot be verified.
    
    주석 처리: JWT 검증 에러 클래스. 현재는 사용하지 않지만 향후 필요할 수 있으므로 유지
    """


# 주석 처리: JWKS URL 해석 함수. 현재는 사용하지 않음
# def _resolve_jwks_url() -> str:
#     if settings.JAVA_BACKEND_JWKS_URL:
#         return settings.JAVA_BACKEND_JWKS_URL
#     base = settings.JAVA_BACKEND_BASE_URL.rstrip("/")
#     return f"{base}/.well-known/jwks.json"


# 주석 처리: JWT 알고리즘 설정 함수. 현재는 사용하지 않음
# def _get_algorithms() -> List[str]:
#     algorithms = [
#         alg.strip()
#         for alg in settings.JAVA_BACKEND_JWT_ALGORITHMS.split(",")
#         if alg.strip()
#     ]
#     return algorithms or ["RS256"]


# 주석 처리: JWKS 클라이언트 초기화 함수. 현재는 사용하지 않음
# def _get_jwks_client() -> PyJWKClient:
#     global _jwks_client, _jwks_client_url
#     url = _resolve_jwks_url()
#     if _jwks_client is None or _jwks_client_url != url:
#         logger.info("Initializing PyJWKClient for JWKS URL: %s", url)
#         _jwks_client = PyJWKClient(url)
#         _jwks_client_url = url
#     return _jwks_client


# 주석 처리: JWT 디코딩 함수. 현재는 사용하지 않음
# async def _decode_jwt(
#     token: str,
#     *,
#     audience: Optional[str],
#     issuer: Optional[str],
#     algorithms: Optional[List[str]] = None,
# ) -> Dict[str, Any]:
#     client = _get_jwks_client()
# 
#     try:
#         signing_key = await asyncio.to_thread(client.get_signing_key_from_jwt, token)
#         decoded = jwt.decode(
#             token,
#             signing_key.key,
#             algorithms=algorithms or _get_algorithms(),
#             audience=audience,
#             issuer=issuer,
#             options={
#                 "verify_aud": audience is not None,
#                 "verify_iss": issuer is not None,
#             },
#         )
#         return decoded
#     except InvalidTokenError as exc:
#         logger.warning("JWT verification failed: %s", exc)
#         raise JWTVerificationError(str(exc)) from exc
#     except Exception as exc:
#         logger.error("Unexpected error verifying JWT: %s", exc)
#         raise JWTVerificationError("Failed to verify JWT") from exc


# 주석 처리: 사용자 JWT 검증 함수. TS 직접 통신 시 사용했던 함수. 현재는 사용하지 않음
# async def verify_jwt(token: str) -> Dict[str, Any]:
#     """Verify a user JWT issued by the Java backend and return its payload.
#     
#     주석 처리: TS 직접 통신 시 사용했던 함수. 현재는 Java 서버를 통해 내부 통신하므로 사용하지 않음
#     """
#     return await _decode_jwt(
#         token,
#         audience=settings.JAVA_BACKEND_JWT_AUDIENCE,
#         issuer=settings.JAVA_BACKEND_JWT_ISSUER,
#         algorithms=_get_algorithms(),
#     )


# 주석 처리: 서비스 간 JWT 검증 함수. 서비스 간 JWT 통신 시 사용했던 함수. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
# async def verify_service_jwt(token: str) -> Dict[str, Any]:
#     """Verify a service-to-service JWT issued by the Java backend.
#     
#     주석 처리: 서비스 간 JWT 통신 시 사용했던 함수. 현재는 같은 EC2 내부 통신이므로 JWT 불필요
#     """
#     service_algorithms = getattr(
#         settings,
#         "JAVA_BACKEND_SERVICE_JWT_ALGORITHMS",
#         settings.JAVA_BACKEND_JWT_ALGORITHMS,
#     ) or settings.JAVA_BACKEND_JWT_ALGORITHMS
#     algorithms = [
#         alg.strip()
#         for alg in service_algorithms.split(",")
#         if alg.strip()
#     ] or _get_algorithms()
# 
#     return await _decode_jwt(
#         token,
#         audience=getattr(settings, "JAVA_BACKEND_SERVICE_JWT_AUDIENCE", None),
#         issuer=getattr(settings, "JAVA_BACKEND_SERVICE_JWT_ISSUER", None),
#         algorithms=algorithms,
#     )

