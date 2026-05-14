"""Pydantic schemas for LLM internal API."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

_MAX_HISTORY_MESSAGES = 100
_MAX_CHAT_MESSAGE_CHARS = 32_000


class ChatMessage(BaseModel):
    """One chat turn (Java may load from NoSQL and pass in the request body)."""

    role: Literal["system", "user", "assistant"]
    content: str = Field(..., max_length=_MAX_CHAT_MESSAGE_CHARS)


class LLMExecuteRequest(BaseModel):
    """Request body for POST /internal/v1/llm/execute and /execute/stream."""

    user_id: int = Field(..., description="User ID from Java server")
    prompt: str = Field(..., description="This turn user message")
    history: List[ChatMessage] = Field(
        default_factory=list,
        description="Prior turns (e.g. from Java NoSQL). Max 100 messages",
        max_length=_MAX_HISTORY_MESSAGES,
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra JSON context (metadata, snippets, etc.)",
    )
    model: Optional[str] = Field(None, description="OpenAI model id override")
    max_iterations: int = Field(
        5,
        description="Reserved for future multi-round tool loops",
        ge=1,
        le=20,
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": 123,
                "prompt": "Summarize recent auth changes for a blog draft",
                "history": [
                    {"role": "user", "content": "Hi"},
                    {"role": "assistant", "content": "Hello. How can I help?"},
                ],
                "context": {"note": "optional"},
                "model": "gpt-4-turbo-preview",
            }
        }
    )


class LLMFinalArtifact(BaseModel):
    """Structured final output from the second-stage LLM."""

    answer: str = Field(..., description="Short reply for chat/UI")
    blog_markdown: str = Field(..., description="Full markdown draft")


class ToolCall(BaseModel):
    """One executed tool and its outcome."""

    tool: str
    params: Dict[str, Any]
    result: Any
    success: bool = True


class LLMExecuteResult(BaseModel):
    """Response body for POST /internal/v1/llm/execute."""

    model_config = ConfigDict(protected_namespaces=())

    ok: bool
    thought: Optional[str] = None
    tool_calls: List[ToolCall]
    final_response: str
    final_artifact: Optional[LLMFinalArtifact] = None
    model_used: Optional[str] = None
