"""Tool for posting blog articles."""
from typing import Dict, Any
from src.adapters import blog_api
from src.server.settings import settings

TOOL = {
    "name": "post_blog_article",
    "title": "Post Blog Article",
    "description": "Publish an article to the blog platform",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Article title"
            },
            "markdown": {
                "type": "string",
                "description": "Article content in markdown format"
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of tags"
            }
        },
        "required": ["title", "markdown"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the tool.
    
    Args:
        params: Tool parameters (title, markdown, tags)
            - api_key는 선택사항이며, 제공되지 않으면 settings.BLOG_API_KEY 사용
        
    Returns:
        Execution result
    """
    title = params.get("title")
    markdown = params.get("markdown")
    tags = params.get("tags", [])
    # API 키는 params에서 가져오거나 settings에서 가져옴 (Python 서버 .env 사용)
    api_key = params.get("api_key") or settings.BLOG_API_KEY

    if not api_key:
        raise ValueError("BLOG_API_KEY is required in settings or api_key must be provided in params")

    result = await blog_api.publish_article(
        title=title,
        markdown=markdown,
        tags=tags,
        api_key=api_key,
    )
    
    return {
        "success": True,
        "article": result
    }

