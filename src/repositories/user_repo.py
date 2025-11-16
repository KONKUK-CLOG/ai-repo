"""User repository backed by the external Java backend service."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

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

    async def sync_github_user(self, github_profile: Dict[str, Any]) -> Tuple[User, str]:
        """Send GitHub user data to the Java backend and obtain the user + API key."""
        logger.info(
            "Syncing GitHub user with Java backend: github_id=%s login=%s",
            github_profile.get("github_id"),
            github_profile.get("username"),
        )

        try:
            payload = await java_backend.upsert_github_user(github_profile)
        except httpx.HTTPError as exc:
            logger.error("Java backend user sync failed: %s", exc)
            raise

        user_payload = _extract_user_payload(payload)
        api_key = payload.get("api_key")

        if not api_key:
            raise ValueError("Java backend response missing 'api_key'")

        user = User.from_backend(user_payload)
        return user, api_key

    async def get_by_id(self, user_id: int) -> Optional[User]:
        """Fetch a user by ID using the service credentials."""
        try:
            payload = await java_backend.get_user_by_id(user_id)
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

    async def get_by_api_key(self, api_key: str) -> Optional[User]:
        """Fetch a user profile using their API key."""
        try:
            payload = await java_backend.get_user_by_api_key(api_key)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403, 404):
                logger.warning("API key rejected by Java backend: %s", exc)
                return None
            logger.error("Failed to resolve user via API key: %s", exc)
            raise
        except httpx.HTTPError as exc:
            logger.error("Failed to resolve user via API key: %s", exc)
            raise

        user_payload = _extract_user_payload(payload)
        return User.from_backend(user_payload)


# 전역 user repository 인스턴스
user_repo = UserRepository()

