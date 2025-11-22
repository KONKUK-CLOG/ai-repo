"""Tool for retrieving user's blog post history."""
from typing import Dict, Any
from src.adapters import blog_api

TOOL = {
    "name": "get_user_blog_posts",
    "title": "Get User Blog Posts",
    "description": "Retrieve user's blog post history to understand writing style, topics, and tag patterns",
    "input_schema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "integer",
                "description": "User ID to retrieve blog posts for"
            },
            "limit": {
                "type": "integer",
                "description": "Number of posts to retrieve (default: 10)",
                "default": 10
            },
            "offset": {
                "type": "integer",
                "description": "Pagination offset (default: 0)",
                "default": 0
            }
        },
        "required": ["user_id"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the tool.
    
    Args:
        params: Tool parameters
            - user_id: User ID (required)
            - limit: Number of posts to retrieve (optional, default: 10)
            - offset: Pagination offset (optional, default: 0)
        
    Returns:
        Execution result containing blog posts and metadata
        {
            "posts": [
                {
                    "id": "string",
                    "title": "string",
                    "content": "string",
                    "tags": ["string"],
                    "created_at": "ISO8601 datetime",
                    "updated_at": "ISO8601 datetime"
                }
            ],
            "total": int,
            "limit": int,
            "offset": int
        }
    
    Raises:
        ValueError: If user_id is not provided
    """
    user_id = params.get("user_id")
    if user_id is None:
        raise ValueError("user_id is required")
    
    limit = params.get("limit", 10)
    offset = params.get("offset", 0)
    
    result = await blog_api.get_user_articles(
        user_id=user_id,
        limit=limit,
        offset=offset,
    )
    
    return result

