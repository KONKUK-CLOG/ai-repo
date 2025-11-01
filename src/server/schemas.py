"""Pydantic schemas for request/response models."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# Diff Schemas
class DiffFileItem(BaseModel):
    """Individual file change in diff."""
    path: str
    status: Literal["added", "modified", "deleted"]
    before: Optional[str] = None
    after: Optional[str] = None


class DiffApplyRequest(BaseModel):
    """Request to apply code diff."""
    unified: Optional[str] = Field(None, description="Unified diff patch string")
    files: Optional[List[DiffFileItem]] = Field(None, description="Array of file changes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "files": [
                    {
                        "path": "src/main.py",
                        "status": "modified",
                        "before": "print('hello')",
                        "after": "print('hello world')"
                    }
                ]
            }
        }


class DiffApplyResult(BaseModel):
    """Result of applying diff."""
    ok: bool
    files_processed: int
    embeddings_upserted: int
    graph_nodes_updated: int
    stats: Dict[str, Any] = Field(default_factory=dict)


# Command Schemas
class CommandExecuteRequest(BaseModel):
    """Request to execute a command/tool."""
    name: str = Field(..., description="Tool name to execute")
    params: Dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "post_blog_article",
                "params": {
                    "title": "My Article",
                    "markdown": "# Hello World"
                }
            }
        }


class CommandExecuteResult(BaseModel):
    """Result of command execution."""
    ok: bool
    tool: str
    result: Any


class ToolSchema(BaseModel):
    """Schema definition for a tool."""
    name: str
    title: str
    description: str
    input_schema: Dict[str, Any]


class CommandsListResponse(BaseModel):
    """List of available commands/tools."""
    tools: List[ToolSchema]


# Error Schema
class ErrorDetail(BaseModel):
    """Error detail structure."""
    type: str
    message: str
    code: Optional[str] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response wrapper."""
    error: ErrorDetail

