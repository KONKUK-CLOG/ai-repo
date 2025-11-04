"""Dependency injection for FastAPI routes.

FastAPI 라우트에서 사용하는 의존성 주입 함수들입니다.
사용자 인증 및 권한 검증을 처리합니다.
"""
from fastapi import Header, HTTPException, status
from src.models.user import User
from src.repositories.user_repo import user_repo


async def get_current_user(x_api_key: str = Header(..., description="User API key")) -> User:
    """API 키로 현재 사용자를 조회합니다.
    
    요청 헤더의 x-api-key를 사용하여 사용자를 인증하고,
    User 객체를 반환합니다. 이후 라우트 핸들러에서 user.id를 사용하여
    사용자별 데이터를 격리합니다.
    
    Args:
        x_api_key: 요청 헤더의 API 키 (x-api-key)
        
    Returns:
        인증된 User 객체
        
    Raises:
        HTTPException: 401 - API 키가 유효하지 않음
        
    Example:
        >>> @router.get("/some-endpoint")
        >>> async def endpoint(user: User = Depends(get_current_user)):
        >>>     # user.id로 사용자 데이터 접근
        >>>     return {"user_id": user.id, "username": user.username}
    """
    # API 키로 사용자 조회
    user = await user_repo.get_by_api_key(x_api_key)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key. Please authenticate via /auth/github/login"
        )
    
    # 마지막 로그인 시각 업데이트 (비동기, 백그라운드에서)
    # 모든 요청마다 업데이트하면 부하가 클 수 있으므로,
    # 필요시 주석 처리하거나 일정 시간 간격으로만 업데이트 가능
    # await user_repo.update_last_login(user.id)
    
    return user

