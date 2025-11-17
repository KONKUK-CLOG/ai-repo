"""User repository backed by the external Java backend service."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from src.adapters import java_backend
from src.models.user import User

logger = logging.getLogger(__name__)


def _extract_user_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    user_payload = data.get("user")
    if isinstance(user_payload, dict):
        return user_payload
    return data


class UserRepository:
    """Proxy user repository interacting with the Java backend."""

    async def get_by_id(self, user_id: int, bearer_token: Optional[str] = None) -> Optional[User]:
        """Fetch a user by ID using the provided JWT token.
        
        Args:
            user_id: 사용자 ID
            bearer_token: Java 서버로 전달할 JWT 토큰 (선택적)
        """
        try:
            payload = await java_backend.get_user_by_id(user_id, bearer_token=bearer_token)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.info("User %s not found in Java backend", user_id)
                return None
            logger.error("Failed to fetch user %s from Java backend: %s", user_id, exc)
            raise
        except httpx.HTTPError as exc:
            logger.error("Failed to fetch user %s from Java backend: %s", user_id, exc)
            raise

        user_payload = _extract_user_payload(payload)
        return User.from_backend(user_payload)


# 전역 user repository 인스턴스
user_repo = UserRepository()

