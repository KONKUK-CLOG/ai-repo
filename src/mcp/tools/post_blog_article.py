"""Tool for posting blog articles."""
from typing import Dict, Any
from src.adapters import blog_api

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
        
    Returns:
        Execution result
    """
    title = params.get("title")
    markdown = params.get("markdown")
    tags = params.get("tags", [])
    
    result = await blog_api.publish_article(
        title=title,
        markdown=markdown,
        tags=tags
    )
    
    return {
        "success": True,
        "article": result
    }

