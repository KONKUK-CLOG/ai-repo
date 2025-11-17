"""GitHub adapter for git operations and OAuth authentication.

GitHub OAuth 2.0 인증 및 git 작업을 처리합니다.
"""
import logging
import httpx
from typing import Dict, Any, Optional
from src.server.settings import settings

logger = logging.getLogger(__name__)


async def exchange_code_for_token(code: str) -> Optional[str]:
    """GitHub OAuth code를 access token으로 교환합니다.
    
    OAuth 인증 플로우의 두 번째 단계입니다.
    사용자가 GitHub에서 인증한 후 받은 code를 access token으로 교환합니다.
    
    Args:
        code: GitHub OAuth authorization code
        
    Returns:
        Access token 문자열, 실패 시 None
        
    Raises:
        httpx.HTTPError: GitHub API 호출 실패
    """
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        logger.error("GitHub OAuth credentials not configured")
        return None
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                headers={"Accept": "application/json"},
                data={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            access_token = data.get("access_token")
            if not access_token:
                logger.error(f"No access token in response: {data}")
                return None
            
            logger.info("Successfully exchanged code for access token")
            return access_token
            
    except httpx.HTTPError as e:
        logger.error(f"Failed to exchange code for token: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during token exchange: {e}")
        return None


async def get_user_info(access_token: str) -> Optional[Dict[str, Any]]:
    """GitHub access token으로 사용자 정보를 가져옵니다.
    
    GitHub API를 호출하여 인증된 사용자의 정보를 조회합니다.
    
    Args:
        access_token: GitHub OAuth access token
        
    Returns:
        사용자 정보 딕셔너리:
            - id: GitHub 사용자 ID (int)
            - login: 사용자명 (str)
            - email: 이메일 (str, optional)
            - name: 표시 이름 (str, optional)
            - avatar_url: 프로필 이미지 URL (str)
        실패 시 None
        
    Raises:
        httpx.HTTPError: GitHub API 호출 실패
    """
    try:
        async with httpx.AsyncClient() as client:
            # 기본 사용자 정보 가져오기
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {access_token}",
                    "X-GitHub-Api-Version": "2022-11-28"
                }
            )
            
            response.raise_for_status()
            user_data = response.json()
            
            # 이메일이 없는 경우 별도 엔드포인트에서 가져오기
            email = user_data.get("email")
            if not email:
                try:
                    email_response = await client.get(
                        "https://api.github.com/user/emails",
                        headers={
                            "Accept": "application/vnd.github+json",
                            "Authorization": f"Bearer {access_token}",
                            "X-GitHub-Api-Version": "2022-11-28"
                        }
                    )
                    email_response.raise_for_status()
                    emails = email_response.json()
                    
                    # Primary email 찾기
                    for email_item in emails:
                        if email_item.get("primary"):
                            email = email_item.get("email")
                            break
                    
                    # Primary가 없으면 첫 번째 이메일 사용
                    if not email and emails:
                        email = emails[0].get("email")
                        
                except Exception as e:
                    logger.warning(f"Failed to fetch user emails: {e}")
            
            result = {
                "id": user_data["id"],
                "login": user_data["login"],
                "email": email,
                "name": user_data.get("name"),
                "avatar_url": user_data.get("avatar_url")
            }
            
            logger.info(f"Successfully fetched user info for {result['login']}")
            return result
            
    except httpx.HTTPError as e:
        logger.error(f"Failed to fetch user info: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching user info: {e}")
        return None

