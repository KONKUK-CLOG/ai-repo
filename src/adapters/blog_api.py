"""Blog API adapter for publishing articles via the Java backend."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from src.adapters import java_backend

logger = logging.getLogger(__name__)


async def publish_article(
    *,
    title: str,
    markdown: str,
    tags: Optional[List[str]] = None,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish an article through the Java backend blog API."""
    if not api_key:
        raise ValueError("api_key is required to publish a blog article")

    payload = {
        "title": title,
        "content": markdown,
        "tags": tags or [],
    }

    try:
        response = await java_backend.create_blog_post(api_key, payload)
    except httpx.HTTPError as exc:
        logger.error("Failed to publish blog article via Java backend: %s", exc)
        raise

    logger.info("Blog article published via Java backend")
    return response

