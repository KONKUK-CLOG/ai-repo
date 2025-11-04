"""Authentication endpoints for GitHub OAuth.

GitHub OAuth 2.0을 사용한 사용자 인증 엔드포인트입니다.

인증 플로우:
1. 클라이언트: GET /auth/github/login → GitHub로 리다이렉트
2. 사용자: GitHub에서 로그인 및 권한 승인
3. GitHub: /auth/github/callback?code=xxx로 리다이렉트
4. 서버: code를 access token으로 교환
5. 서버: GitHub API에서 사용자 정보 조회
6. 서버: DB에 사용자 upsert (없으면 생성, 있으면 업데이트)
7. 서버: API 키 반환 (클라이언트는 이후 x-api-key 헤더에 사용)
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from src.server.settings import settings
from src.server.schemas import AuthCallbackResponse, UserPublic
from src.adapters import github
from src.repositories.user_repo import user_repo
import logging
import urllib.parse

router = APIRouter(prefix="/auth/github", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/login")
async def github_login():
    """GitHub OAuth 인증 시작.
    
    사용자를 GitHub 인증 페이지로 리다이렉트합니다.
    GitHub에서 인증 후 /auth/github/callback으로 돌아옵니다.
    
    Query Parameters:
        redirect_url: (Optional) 인증 후 돌아갈 클라이언트 URL
    
    Returns:
        RedirectResponse: GitHub OAuth 인증 페이지로 리다이렉트
    
    Raises:
        HTTPException: 500 - GitHub OAuth가 설정되지 않음
    
    Example:
        >>> GET /auth/github/login
        >>> (Redirects to GitHub)
    """
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth not configured. Please set GITHUB_CLIENT_ID."
        )
    
    # GitHub OAuth 인증 URL 생성
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "redirect_uri": settings.GITHUB_REDIRECT_URI,
        "scope": "read:user user:email",  # 사용자 정보 및 이메일 읽기
    }
    
    github_auth_url = f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    
    logger.info(f"Redirecting to GitHub OAuth: {github_auth_url}")
    return RedirectResponse(url=github_auth_url)


@router.get("/callback", response_model=AuthCallbackResponse)
async def github_callback(code: str):
    """GitHub OAuth callback 처리.
    
    GitHub에서 인증 후 돌아오는 엔드포인트입니다.
    OAuth code를 access token으로 교환하고, 사용자 정보를 조회하여
    DB에 저장한 후 API 키를 반환합니다.
    
    처리 과정:
    1. OAuth code → access token 교환
    2. Access token으로 GitHub 사용자 정보 조회
    3. DB에 사용자 upsert (없으면 생성, 있으면 last_login 업데이트)
    4. API 키 반환 (클라이언트는 이후 요청에 x-api-key 헤더로 사용)
    
    Args:
        code: GitHub OAuth authorization code
    
    Returns:
        AuthCallbackResponse: 인증 성공 응답 (API 키 포함)
    
    Raises:
        HTTPException:
            - 400: code 파라미터 누락
            - 500: Token 교환 실패 또는 사용자 정보 조회 실패
    
    Example:
        >>> GET /auth/github/callback?code=abc123
        >>> Response: {
        >>>     "success": true,
        >>>     "api_key": "550e8400-e29b-41d4-a716-446655440000",
        >>>     "user": {...},
        >>>     "message": "Successfully authenticated"
        >>> }
    """
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' parameter"
        )
    
    logger.info(f"Processing GitHub OAuth callback (code length: {len(code)})")
    
    # 1. Code → Access Token 교환
    access_token = await github.exchange_code_for_token(code)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to exchange code for access token"
        )
    
    # 2. Access Token으로 사용자 정보 조회
    user_info = await github.get_user_info(access_token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user information from GitHub"
        )
    
    logger.info(f"GitHub user authenticated: {user_info['login']} (id={user_info['id']})")
    
    # 3. DB에 사용자 upsert
    user = await user_repo.upsert(
        github_id=user_info["id"],
        username=user_info["login"],
        email=user_info.get("email"),
        name=user_info.get("name")
    )
    
    # 4. API 키 반환
    user_public = UserPublic(
        id=user.id,
        github_id=user.github_id,
        username=user.username,
        email=user.email,
        name=user.name,
        created_at=user.created_at,
        last_login=user.last_login
    )
    
    response = AuthCallbackResponse(
        success=True,
        api_key=user.api_key,
        user=user_public,
        message=f"Successfully authenticated as {user.username}"
    )
    
    logger.info(f"User {user.username} (id={user.id}) authenticated successfully")
    
    return response


@router.get("/logout")
async def github_logout():
    """로그아웃 엔드포인트.
    
    현재는 stateless 인증(API 키 기반)이므로 서버에서 할 일이 없습니다.
    클라이언트가 API 키를 삭제하면 됩니다.
    
    Returns:
        메시지: 로그아웃 안내
    
    Example:
        >>> GET /auth/github/logout
        >>> Response: {
        >>>     "message": "Please delete your API key from the client"
        >>> }
    """
    return {
        "message": "Logout successful. Please delete your API key from the client.",
        "note": "This is a stateless authentication system. The server does not track sessions."
    }

