"""Blog API adapter for publishing articles."""
import logging
from typing import Dict, Any
from src.server.settings import settings

logger = logging.getLogger(__name__)


async def publish_article(title: str, markdown: str, tags: list[str] = None) -> Dict[str, Any]:
    """Publish article to blog platform.
    
    Args:
        title: Article title
        markdown: Article content in markdown
        tags: Optional list of tags
        
    Returns:
        Publication result with article ID and URL
    """
    logger.info(f"Publishing article to blog: {title}")
    logger.info(f"Blog API URL: {settings.BLOG_API_URL}")
    
    # Dummy implementation - would make actual HTTP request here
    # Example:
    # async with httpx.AsyncClient() as client:
    #     response = await client.post(
    #         f"{settings.BLOG_API_URL}/articles",
    #         headers={"Authorization": f"Bearer {settings.BLOG_API_KEY}"},
    #         json={"title": title, "content": markdown, "tags": tags}
    #     )
    #     return response.json()
    
    return {
        "article_id": "dummy-123",
        "url": f"{settings.BLOG_API_URL}/articles/dummy-123",
        "title": title,
        "published": True
    }

