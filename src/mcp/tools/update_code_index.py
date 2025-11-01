"""Tool for updating code index incrementally."""
from typing import Dict, Any, List
from src.adapters import vector_db, graph_db
from src.server.settings import settings

TOOL = {
    "name": "update_code_index",
    "title": "Update Code Index",
    "description": "Incrementally update vector and graph indexes with code changes",
    "input_schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": ["added", "modified", "deleted"]
                        }
                    },
                    "required": ["path", "status"]
                },
                "description": "List of file changes"
            }
        },
        "required": ["files"]
    }
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the tool.
    
    Args:
        params: Tool parameters (files)
        
    Returns:
        Execution result
    """
    files = params.get("files", [])
    
    # Prepare documents for vector DB
    documents = []
    file_paths = []
    for file_item in files:
        file_paths.append(file_item["path"])
        if file_item["status"] != "deleted":
            documents.append({
                "file": file_item["path"],
                "content": file_item.get("content", ""),
                "status": file_item["status"]
            })
    
    # Update vector DB
    embeddings_upserted = await vector_db.upsert_embeddings(
        collection=settings.VECTOR_DB_COLLECTION,
        documents=documents
    )
    
    # Update graph DB
    nodes_updated = await graph_db.update_code_graph(files=file_paths)
    
    return {
        "success": True,
        "files_processed": len(files),
        "embeddings_upserted": embeddings_upserted,
        "graph_nodes_updated": nodes_updated
    }

