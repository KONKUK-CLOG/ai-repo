"""Tool for publishing to Notion."""
from typing import Dict, Any, Optional
from src.adapters import notion

TOOL = {
    "name": "publish_to_notion",
    "title": "Publish to Notion",
    "description": "Publish a page to Notion workspace",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Page title"
            },
            "content": {
                "type": "string",
                "description": "Page content (markdown or text)"
            },
            "parent_page_id": {
                "type": "string",
                "description": "Optional parent page ID"
            }
        },
        "required": ["title", "content"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the tool.
    
    Args:
        params: Tool parameters (title, content, parent_page_id)
        
    Returns:
        Execution result
    """
    title = params.get("title")
    content = params.get("content")
    parent_page_id = params.get("parent_page_id")
    
    result = await notion.publish_page(
        title=title,
        content=content,
        parent_page_id=parent_page_id
    )
    
    return {
        "success": True,
        "page": result
    }

