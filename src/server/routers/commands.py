"""Command execution endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional
from src.server.deps import verify_api_key
from src.server.schemas import (
    CommandExecuteRequest,
    CommandExecuteResult,
    CommandsListResponse,
    ToolSchema,
    ErrorResponse,
    ErrorDetail
)
from src.mcp.tools import (
    post_blog_article,
    update_code_index,
    refresh_rag_indexes,
    publish_to_notion,
    create_commit_and_push
)
import logging
import uuid

router = APIRouter(prefix="/api/v1/commands", tags=["commands"])
logger = logging.getLogger(__name__)

# Registry of available tools
TOOLS_REGISTRY = {
    "post_blog_article": post_blog_article,
    "update_code_index": update_code_index,
    "refresh_rag_indexes": refresh_rag_indexes,
    "publish_to_notion": publish_to_notion,
    "create_commit_and_push": create_commit_and_push,
}


@router.get("", response_model=CommandsListResponse)
async def list_commands(
    api_key: str = Depends(verify_api_key)
) -> CommandsListResponse:
    """List all available commands/tools with their schemas.
    
    Args:
        api_key: Validated API key
        
    Returns:
        List of tool schemas
    """
    tools = []
    for tool_name, tool_module in TOOLS_REGISTRY.items():
        if hasattr(tool_module, "TOOL"):
            tool_def = tool_module.TOOL
            tools.append(ToolSchema(
                name=tool_def["name"],
                title=tool_def.get("title", tool_def["name"]),
                description=tool_def.get("description", ""),
                input_schema=tool_def.get("input_schema", {})
            ))
    
    return CommandsListResponse(tools=tools)


@router.post("/execute", response_model=CommandExecuteResult)
async def execute_command(
    request: CommandExecuteRequest,
    api_key: str = Depends(verify_api_key),
    x_idempotency_key: Optional[str] = Header(None)
) -> CommandExecuteResult:
    """Execute a command/tool.
    
    Args:
        request: Command execution request
        api_key: Validated API key
        x_idempotency_key: Optional idempotency key for duplicate prevention
        
    Returns:
        Command execution result
        
    Raises:
        HTTPException: 400 if tool not found, 500 if execution fails
    """
    # Generate or use provided idempotency key
    idempotency_key = x_idempotency_key or str(uuid.uuid4())
    logger.info(f"Executing command '{request.name}' with idempotency key: {idempotency_key}")
    
    # Check if tool exists
    if request.name not in TOOLS_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool '{request.name}' not found"
        )
    
    tool_module = TOOLS_REGISTRY[request.name]
    
    try:
        # Execute the tool
        if hasattr(tool_module, "run"):
            result = await tool_module.run(request.params)
            
            return CommandExecuteResult(
                ok=True,
                tool=request.name,
                result=result
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Tool '{request.name}' has no run method"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing command '{request.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "type": type(e).__name__,
                    "message": str(e),
                    "code": "EXECUTION_ERROR",
                    "request_id": idempotency_key
                }
            }
        )

