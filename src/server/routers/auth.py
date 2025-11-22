"""Authentication namespace placeholder.

GitHub 소셜 로그인 및 사용자 JWT 발급은 TS ↔ Java 서버 사이에서만 처리됩니다.
Python 서버는 인증에 관여하지 않으며, Java 서버를 통해 내부 통신합니다.

주석 처리: 이전에는 JWT 검증 및 서비스 간 인증을 담당했으나,
현재는 같은 EC2 내부 통신이므로 JWT 검증이 불필요합니다.

이 모듈은 FastAPI 라우터 구조 유지를 위해 남겨두었습니다.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/auth/github", tags=["auth"])
