"""Tool for searching code relationships in graph database."""
from typing import Dict, Any
from src.adapters import graph_db

TOOL = {
    "name": "search_graph_db",
    "title": "Search Graph Database",
    "description": "Search for code entities (functions, classes) and their relationships based on structure and connections. Returns entities with their call relationships. Note: user_id is automatically provided.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to find matching code entities by name"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 10)",
                "default": 10
            }
        },
        "required": ["query"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute graph-based search for code entities.
    
    Args:
        params: Tool parameters
            - query: Search query string
            - limit: Maximum number of results (default: 10)
            - user_id: User ID for filtering
        
    Returns:
        Search results with entity information and relationships
    """
    query = params.get("query")
    limit = params.get("limit", 10)
    user_id = params.get("user_id")
    
    if not query:
        return {
            "success": False,
            "error": "Query parameter is required"
        }
    
    if user_id is None:
        return {
            "success": False,
            "error": "user_id parameter is required"
        }
    
    # Perform graph search
    results = await graph_db.search_related_code(
        query=query,
        user_id=user_id,
        limit=limit
    )
    
    # Format results
    formatted_results = []
    for result in results:
        formatted_results.append({
            "file": result.get("file", ""),
            "entity_name": result.get("entity_name", ""),
            "entity_type": result.get("entity_type", ""),
            "line_start": result.get("line_start"),
            "line_end": result.get("line_end"),
            "calls": result.get("calls", []),
            "description": result.get("description", ""),
            "keyword_matched": result.get("keyword_matched", "")
        })
    
    return {
        "success": True,
        "results": formatted_results,
        "total_results": len(formatted_results),
        "query": query,
        "limit": limit
    }

