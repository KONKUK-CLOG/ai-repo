"""Tool for semantic search in vector database."""
from typing import Dict, Any
from src.adapters import vector_db
from src.server.settings import settings

TOOL = {
    "name": "search_vector_db",
    "title": "Search Vector Database",
    "description": "Perform semantic search for relevant code content using embeddings. Returns code files with similar meaning to the query. Note: user_id is automatically provided.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query to find semantically similar code"
            },
            "top_k": {
                "type": "integer",
                "description": "Number of top results to return (default: 10)",
                "default": 10
            }
        },
        "required": ["query"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute semantic search in vector database.
    
    Args:
        params: Tool parameters
            - query: Search query string
            - top_k: Number of results to return (default: 10)
            - user_id: User ID for filtering
        
    Returns:
        Search results with file paths, content previews, and scores
    """
    query = params.get("query")
    top_k = params.get("top_k", 10)
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
    
    # Perform semantic search
    results = await vector_db.semantic_search(
        collection=settings.VECTOR_DB_COLLECTION,
        query=query,
        user_id=user_id,
        top_k=top_k
    )
    
    # Format results
    formatted_results = []
    for result in results:
        formatted_results.append({
            "file": result.get("file", ""),
            "content_preview": result.get("content", ""),
            "score": result.get("score", 0.0),
            "content_length": result.get("content_length", 0),
            "updated_at": result.get("updated_at", "")
        })
    
    return {
        "success": True,
        "results": formatted_results,
        "total_results": len(formatted_results),
        "query": query,
        "top_k": top_k
    }

