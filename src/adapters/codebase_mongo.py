"""MongoDB adapter for codebase chunk search (user-scoped text match)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from src.server.settings import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    """Lazy singleton Motor client. Lambda: connection pooling across warm invocations."""
    global _client
    if _client is None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as e:
            raise RuntimeError(
                "motor is required for codebase Mongo search; pip install motor"
            ) from e
        uri = settings.CODEBASE_MONGO_URI
        if not uri:
            raise RuntimeError("CODEBASE_MONGO_URI is not configured")
        _client = AsyncIOMotorClient(uri)
    return _client


async def search_chunks(user_id: int, query: str, top_k: int) -> List[Dict[str, Any]]:
    """Find codebase chunks for user_id where content contains query (case-insensitive).

    Query string is passed through re.escape before use in $regex to avoid ReDoS.

    Raises:
        RuntimeError: Mongo URI missing or motor not installed.
    """
    if not query or not query.strip():
        return []

    client = _get_client()
    uid_field = settings.CODEBASE_MONGO_USER_ID_FIELD
    path_field = settings.CODEBASE_MONGO_PATH_FIELD
    content_field = settings.CODEBASE_MONGO_CONTENT_FIELD
    db_name = settings.CODEBASE_MONGO_DB
    coll_name = settings.CODEBASE_MONGO_COLLECTION
    preview_max = max(1, settings.CODEBASE_MONGO_PREVIEW_MAX_CHARS)

    escaped = re.escape(query.strip())
    filt: Dict[str, Any] = {
        uid_field: user_id,
        content_field: {"$regex": escaped, "$options": "i"},
    }

    collection = client[db_name][coll_name]
    cursor = collection.find(
        filt,
        projection={path_field: 1, content_field: 1},
        limit=max(1, min(top_k, 100)),
    )

    out: List[Dict[str, Any]] = []
    async for doc in cursor:
        raw_content = doc.get(content_field) or ""
        if isinstance(raw_content, str):
            preview = raw_content[:preview_max]
        else:
            preview = str(raw_content)[:preview_max]
        path_val = doc.get(path_field, "")
        oid = doc.get("_id")
        out.append(
            {
                "path": str(path_val) if path_val is not None else "",
                "content_preview": preview,
                "content_length": len(raw_content) if isinstance(raw_content, str) else 0,
                "id": str(oid) if oid is not None else "",
            }
        )

    logger.info("codebase_mongo: user_id=%s query=%r hits=%s", user_id, query[:80], len(out))
    return out
