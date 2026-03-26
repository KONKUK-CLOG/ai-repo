"""Tool: search indexed codebase chunks in MongoDB."""
from typing import Any, Dict

from src.adapters import codebase_mongo
from src.server.settings import settings

TOOL = {
    "name": "search_codebase",
    "title": "Search Codebase",
    "description": (
        "Search stored codebase chunks in MongoDB for the current user. "
        "Use when the user asks about code location, implementation, bugs, refactoring, or architecture "
        "and answers should be grounded in their indexed repository. "
        "The server injects user_id automatically; do not guess user_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language or keyword search string to match inside chunk content",
            },
            "top_k": {
                "type": "integer",
                "description": "Max number of chunks to return (default: 10, max: 100)",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


async def run(params: Dict[str, Any]) -> Dict[str, Any]:
    query = params.get("query")
    top_k = int(params.get("top_k", 10) or 10)
    user_id = params.get("user_id")

    if not query or not str(query).strip():
        return {"success": False, "error": "query is required"}
    if user_id is None:
        return {"success": False, "error": "user_id is required"}

    if not settings.CODEBASE_MONGO_URI:
        return {
            "success": False,
            "error": "CODEBASE_MONGO_URI is not configured",
            "results": [],
            "total_results": 0,
        }

    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return {"success": False, "error": "user_id must be an integer"}

    try:
        results = await codebase_mongo.search_chunks(uid, str(query), top_k)
    except RuntimeError as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "total_results": 0,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "results": [],
            "total_results": 0,
        }

    return {
        "success": True,
        "results": results,
        "total_results": len(results),
        "query": str(query).strip(),
        "top_k": top_k,
    }
