"""Service-to-service JWT manager for the Java backend."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, Tuple

import httpx

from src.server.settings import settings

logger = logging.getLogger(__name__)


class ServiceTokenError(RuntimeError):
    """Raised when a service JWT cannot be obtained."""


class ServiceTokenManager:
    """Handles acquisition and rotation of Java service JWTs."""

    def __init__(self) -> None:
        self._token: Optional[str] = settings.JAVA_BACKEND_SERVICE_JWT
        self._expires_at: Optional[int] = None
        self._lock = asyncio.Lock()
        self._refresh_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._base_backoff = max(1, settings.JAVA_BACKEND_SERVICE_REFRESH_BACKOFF_SECONDS)
        self._max_backoff = max(
            self._base_backoff, settings.JAVA_BACKEND_SERVICE_REFRESH_BACKOFF_MAX_SECONDS
        )

    async def startup(self) -> None:
        """Prime the manager and schedule background refresh."""
        if not self._has_refresh_credentials() and not self._token:
            logger.warning(
                "Java service JWT is not configured and no refresh credentials were provided; "
                "Python → Java calls will fail."
            )
            return

        try:
            await self.get_token(force_refresh=not bool(self._token))
        except Exception as exc:  # pragma: no cover - startup log
            logger.error("Failed to obtain initial service JWT: %s", exc)
            raise

        if self._has_refresh_credentials():
            self._start_refresh_loop()

    async def shutdown(self) -> None:
        """Stop background refresh tasks."""
        self._stop_event.set()
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None

    async def get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid service JWT, refreshing it when necessary."""
        async with self._lock:
            if not force_refresh and self._token and not self._is_expiring():
                return self._token

            if not self._has_refresh_credentials():
                if self._token:
                    return self._token
                raise ServiceTokenError(
                    "Service JWT is not configured and refresh credentials are missing."
                )

            await self._refresh_locked()
            assert self._token  # for type-checkers
            return self._token

    async def invalidate(self) -> None:
        """Force the cache to treat the token as expired."""
        async with self._lock:
            self._token = None
            self._expires_at = None

    def _has_refresh_credentials(self) -> bool:
        return bool(
            settings.JAVA_BACKEND_SERVICE_CLIENT_ID
            and settings.JAVA_BACKEND_SERVICE_CLIENT_SECRET
            and settings.JAVA_BACKEND_BASE_URL
        )

    def _refresh_url(self) -> str:
        base = (settings.JAVA_BACKEND_BASE_URL or "").rstrip("/")
        if not base:
            raise ServiceTokenError("JAVA_BACKEND_BASE_URL is not configured.")
        path = settings.JAVA_BACKEND_SERVICE_JWT_REFRESH_PATH or "/api/v1/auth/service-jwt"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _is_expiring(self) -> bool:
        if not self._token:
            return True
        if self._expires_at is None:
            return False
        skew = max(0, settings.JAVA_BACKEND_SERVICE_TOKEN_SKEW_SECONDS)
        return time.time() >= (self._expires_at - skew)

    def _seconds_until_refresh_window(self) -> int:
        if self._expires_at is None:
            return max(5, settings.JAVA_BACKEND_SERVICE_REFRESH_MIN_INTERVAL)
        refresh_time = self._expires_at - max(0, settings.JAVA_BACKEND_SERVICE_TOKEN_SKEW_SECONDS)
        return max(5, int(refresh_time - time.time()))

    async def _refresh_locked(self) -> None:
        token, expires_at = await self._request_new_token()
        self._token = token
        self._expires_at = expires_at
        logger.info(
            "Fetched service JWT from Java backend (expires_at=%s)", self._expires_at or "unset"
        )

    async def _request_new_token(self) -> Tuple[str, Optional[int]]:
        payload = {
            "grant_type": "client_credentials",
            "client_id": settings.JAVA_BACKEND_SERVICE_CLIENT_ID,
            "client_secret": settings.JAVA_BACKEND_SERVICE_CLIENT_SECRET,
        }
        if settings.JAVA_BACKEND_SERVICE_JWT_SCOPE:
            payload["scope"] = settings.JAVA_BACKEND_SERVICE_JWT_SCOPE

        url = self._refresh_url()
        timeout = settings.JAVA_BACKEND_TIMEOUT or 10.0

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            snippet = exc.response.text[:200]
            raise ServiceTokenError(
                f"Service JWT refresh failed with status {exc.response.status_code}: {snippet}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ServiceTokenError("Service JWT refresh request failed") from exc

        data = response.json()
        token = data.get("access_token") or data.get("token") or data.get("jwt")
        if not token:
            raise ServiceTokenError("Service JWT response missing token field.")

        expires_at: Optional[int] = None
        now = int(time.time())
        expires_in = data.get("expires_in")

        for key in ("expires_at", "exp"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                expires_at = int(value)
                break

        if expires_at is None and isinstance(expires_in, (int, float)):
            expires_at = now + int(expires_in)

        return token, expires_at

    def _start_refresh_loop(self) -> None:
        if self._refresh_task:
            return
        self._stop_event.clear()
        self._refresh_task = asyncio.create_task(self._auto_refresh_loop())

    async def _auto_refresh_loop(self) -> None:
        backoff = self._base_backoff
        while not self._stop_event.is_set():
            try:
                wait_seconds = self._seconds_until_refresh_window()
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=wait_seconds)
                    if self._stop_event.is_set():
                        break
                except asyncio.TimeoutError:
                    pass  # expected when it is time to refresh

                await self.get_token(force_refresh=True)
                backoff = self._base_backoff
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Automatic service JWT refresh failed: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._max_backoff)


service_token_manager = ServiceTokenManager()


