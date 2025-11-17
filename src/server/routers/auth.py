"""Authentication namespace placeholder.

GitHub 소셜 로그인 및 사용자 JWT 발급은 TS ↔ Java 서버 사이에서만 처리됩니다.
Python 서버는 인증에 관여하지 않으며, JWT 검증 및 서비스 간 인증만 담당합니다.

이 모듈은 FastAPI 라우터 구조 유지를 위해 남겨두었습니다.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/auth/github", tags=["auth"])
