"""Tool for refreshing RAG indexes globally."""
from typing import Dict, Any
from src.adapters import vector_db, graph_db

TOOL = {
    "name": "refresh_rag_indexes",
    "title": "Refresh RAG Indexes",
    "description": "Globally refresh all vector and graph RAG indexes",
    "input_schema": {
        "type": "object",
        "properties": {
            "full_rebuild": {
                "type": "boolean",
                "description": "Whether to do a full rebuild",
                "default": False
            }
        }
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the tool.
    
    Args:
        params: Tool parameters (full_rebuild)
        
    Returns:
        Execution result
    """
    full_rebuild = params.get("full_rebuild", False)
    
    # Refresh vector indexes
    vector_result = await vector_db.refresh_all_indexes()
    
    # Refresh graph indexes
    graph_result = await graph_db.refresh_graph_indexes()
    
    return {
        "success": True,
        "full_rebuild": full_rebuild,
        "vector_db": vector_result,
        "graph_db": graph_result
    }

