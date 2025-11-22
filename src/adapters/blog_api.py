"""Blog API adapter for retrieving articles via the Java backend."""
from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from src.adapters import java_backend

logger = logging.getLogger(__name__)


async def get_user_articles(
    user_id: int,
    limit: int = 10,
    offset: int = 0,
) -> Dict[str, Any]:
    """Retrieve user's blog articles from the Java backend.
    
    Args:
        user_id: 사용자 ID
        limit: 조회할 포스트 수 (기본값: 10)
        offset: 페이지네이션 오프셋 (기본값: 0)
    
    Returns:
        블로그 포스트 목록 및 메타데이터
        {
            "posts": [...],
            "total": int,
            "limit": int,
            "offset": int
        }
    
    Raises:
        httpx.HTTPError: Java backend 요청 실패 시
    """
    try:
        response = await java_backend.get_user_blog_posts(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        logger.info(f"Retrieved {len(response.get('posts', []))} blog posts for user {user_id}")
        return response
    except httpx.HTTPError as exc:
        logger.error("Failed to retrieve blog articles via Java backend: %s", exc)
        raise

