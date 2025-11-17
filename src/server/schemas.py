"""Pydantic schemas for request/response models.

이 파일은 FastAPI 엔드포인트의 요청/응답 모델을 정의합니다.
모든 스키마는 Pydantic BaseModel을 상속받아 자동 검증 및 문서화를 지원합니다.
"""
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# User & Auth 관련 스키마
# ============================================================================

class UserPublic(BaseModel):
    """공개용 사용자 정보 (API 키 제외).
    
    클라이언트에게 반환할 때 사용하는 모델입니다.
    보안을 위해 API 키는 제외합니다.
    
    Attributes:
        id: 내부 사용자 ID
        github_id: GitHub 사용자 ID
        username: GitHub 사용자명
        email: 사용자 이메일
        name: 사용자 표시 이름
        created_at: 계정 생성 시각
        last_login: 마지막 로그인 시각
    """
    id: int
    github_id: int
    username: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None


class AuthCallbackResponse(BaseModel):
    """GitHub OAuth callback 응답 모델.
    
    인증 성공 후 클라이언트에게 반환되는 정보입니다.
    서버 간 통신용 JWT는 서버 내부에서만 사용되며 클라이언트에는 반환되지 않습니다.
    
    Attributes:
        success: 인증 성공 여부
        user: 사용자 공개 정보
        message: 성공 메시지
    
    Example:
        >>> response = AuthCallbackResponse(
        ...     success=True,
        ...     user=UserPublic(...),
        ...     message="Successfully authenticated"
        ... )
    """
    success: bool
    user: UserPublic
    message: str = Field(default="Successfully authenticated")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "user": {
                    "id": 12345678,
                    "github_id": 12345678,
                    "username": "parkj",
                    "email": "parkj@example.com",
                    "name": "Park J",
                    "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
                    "created_at": None,
                    "last_login": None
                },
                "message": "Successfully authenticated"
            }
        }


# ============================================================================
# Diff 관련 스키마
# ============================================================================

class DiffFileItem(BaseModel):
    """개별 파일 변경사항을 나타내는 모델.
    
    코드 diff를 파일 단위로 표현할 때 사용됩니다.
    
    Attributes:
        path: 파일 경로 (예: "src/main.py")
        status: 변경 타입
            - "added": 새 파일 추가 (after만 필요)
            - "modified": 기존 파일 수정 (before, after 모두 가능)
            - "deleted": 파일 삭제 (before만 필요)
        before: 변경 전 파일 내용 (optional)
        after: 변경 후 파일 내용 (optional)
    
    Example:
        >>> item = DiffFileItem(
        ...     path="src/test.py",
        ...     status="modified",
        ...     before="print('old')",
        ...     after="print('new')"
        ... )
    """
    path: str
    status: Literal["added", "modified", "deleted"]
    before: Optional[str] = None
    after: Optional[str] = None


class DiffApplyRequest(BaseModel):
    """코드 diff 적용 요청 모델.
    
    2가지 입력 모드를 지원합니다:
    1. unified: Git unified diff 패치 문자열
    2. files: 파일 변경사항 배열
    
    둘 중 하나는 반드시 제공되어야 합니다.
    
    Attributes:
        unified: Git unified diff 형식의 패치 문자열
            예: "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@\n-old\n+new"
        files: DiffFileItem 객체 배열
    
    Example (unified 모드):
        >>> request = DiffApplyRequest(
        ...     unified="--- a/test.py\n+++ b/test.py\n..."
        ... )
    
    Example (files 모드):
        >>> request = DiffApplyRequest(
        ...     files=[
        ...         DiffFileItem(
        ...             path="src/main.py",
        ...             status="modified",
        ...             after="print('new')"
        ...         )
        ...     ]
        ... )
    """
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
    """Diff 적용 결과 응답 모델.
    
    벡터 DB와 그래프 DB에 변경사항이 반영된 결과를 담습니다.
    
    Attributes:
        ok: 성공 여부
        files_processed: 처리된 파일 개수
        embeddings_upserted: Vector DB에 업서트(삽입/갱신)된 임베딩 개수
        graph_nodes_updated: Graph DB에 업데이트된 노드 개수
        stats: 추가 통계 정보 (모드, 배치 크기 등)
    
    Example:
        >>> result = DiffApplyResult(
        ...     ok=True,
        ...     files_processed=2,
        ...     embeddings_upserted=2,
        ...     graph_nodes_updated=2,
        ...     stats={"mode": "files", "batch_size": 100}
        ... )
    """
    ok: bool
    files_processed: int
    embeddings_upserted: int
    graph_nodes_updated: int
    stats: Dict[str, Any] = Field(default_factory=dict)



# ============================================================================
# LLM Agent 관련 스키마
# ============================================================================

class LLMExecuteRequest(BaseModel):
    """LLM에게 자연어 명령을 전달하는 요청 모델.
    
    사용자의 자연어 명령을 받아서 LLM이 적절한 툴을 선택하고 실행합니다.
    TS 클라이언트는 사용자 의도만 전달하고, 구체적인 툴 선택은 LLM이 담당합니다.
    
    Attributes:
        prompt: 사용자의 자연어 명령
            예: "이 코드 변경사항을 인덱스에 반영하고 블로그 글도 써줘"
        context: 추가 컨텍스트 정보 (코드 diff, 파일 목록, 메타데이터 등)
        model: 사용할 LLM 모델 (선택사항)
            예: "claude-3-5-sonnet", "gpt-4"
        max_iterations: 최대 반복 횟수 (무한 루프 방지)
    
    Example:
        >>> request = LLMExecuteRequest(
        ...     prompt="이 코드를 인덱스에 추가하고 블로그 글도 써줘",
        ...     context={
        ...         "diff": {"files": [...]},
        ...         "repo": "my-project"
        ...     },
        ...     model="claude-3-5-sonnet"
        ... )
    """
    prompt: str = Field(..., description="사용자의 자연어 명령")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="추가 컨텍스트 정보 (diff, 파일, 메타데이터 등)"
    )
    model: Optional[str] = Field(
        None,
        description="사용할 LLM 모델 (예: claude-3-5-sonnet)"
    )
    max_iterations: int = Field(
        5,
        description="최대 툴 실행 반복 횟수",
        ge=1,
        le=20
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "prompt": "코드 변경사항을 인덱스에 반영하고, 변경 내용을 요약해서 블로그에 올려줘",
                "context": {
                    "diff": {
                        "files": [
                            {
                                "path": "src/main.py",
                                "status": "modified"
                            }
                        ]
                    }
                },
                "model": "claude-3-5-sonnet"
            }
        }


class ToolCall(BaseModel):
    """LLM이 선택하고 실행한 툴 호출 정보.
    
    Attributes:
        tool: 실행된 툴 이름
        params: 툴에 전달된 파라미터
        result: 툴 실행 결과
        success: 실행 성공 여부
    
    Example:
        >>> tool_call = ToolCall(
        ...     tool="post_blog_article",
        ...     params={"title": "My Article", "markdown": "..."},
        ...     result={"article_id": "123", "url": "..."},
        ...     success=True
        ... )
    """
    tool: str
    params: Dict[str, Any]
    result: Any
    success: bool = True


class LLMExecuteResult(BaseModel):
    """LLM 명령 실행 결과 응답 모델.
    
    LLM이 사용자의 자연어 명령을 해석하고, 필요한 툴들을 실행한 결과를 담습니다.
    
    Attributes:
        ok: 전체 작업 성공 여부
        thought: LLM의 사고 과정 또는 추론 내용 (선택사항)
        tool_calls: 실행된 툴들의 목록과 각각의 결과
        final_response: 사용자에게 보여줄 LLM의 최종 응답
        model_used: 실제 사용된 LLM 모델
    
    Example:
        >>> result = LLMExecuteResult(
        ...     ok=True,
        ...     thought="사용자가 블로그 발행과 코드 검색을 요청했음",
        ...     tool_calls=[
        ...         ToolCall(tool="post_blog_article", ...),
        ...         ToolCall(tool="search_vector_db", ...)
        ...     ],
        ...     final_response="블로그 글을 발행하고 관련 코드를 찾았습니다.",
        ...     model_used="claude-3-5-sonnet"
        ... )
    """
    ok: bool
    thought: Optional[str] = None
    tool_calls: List[ToolCall]
    final_response: str
    model_used: Optional[str] = None


# ============================================================================
# Error 관련 스키마
# ============================================================================

class ErrorDetail(BaseModel):
    """에러 상세 정보 모델.
    
    API 에러 발생 시 클라이언트에게 전달할 상세 정보를 담습니다.
    
    Attributes:
        type: 에러 타입 (예: "ValueError", "HTTPException")
        message: 사람이 읽을 수 있는 에러 메시지
        code: 선택적 에러 코드 (예: "TOOL_NOT_FOUND", "EXECUTION_ERROR")
        request_id: 요청 추적용 ID (idempotency key나 자동 생성 ID)
    
    Example:
        >>> error = ErrorDetail(
        ...     type="ToolNotFoundError",
        ...     message="Tool 'invalid_tool' not found",
        ...     code="TOOL_NOT_FOUND",
        ...     request_id="abc-123"
        ... )
    """
    type: str
    message: str
    code: Optional[str] = None
    request_id: Optional[str] = None


class ErrorResponse(BaseModel):
    """에러 응답 래퍼 모델.
    
    일관된 에러 응답 형식을 제공합니다.
    
    Attributes:
        error: ErrorDetail 객체
    
    Example:
        >>> response = ErrorResponse(
        ...     error=ErrorDetail(
        ...         type="HTTPException",
        ...         message="Invalid API key",
        ...         code="UNAUTHORIZED"
        ...     )
        ... )
        
        JSON 형식:
        {
            "error": {
                "type": "HTTPException",
                "message": "Invalid API key",
                "code": "UNAUTHORIZED"
            }
        }
    """
    error: ErrorDetail


# ============================================================================
# Command 관련 스키마
# ============================================================================

class CommandExecuteRequest(BaseModel):
    """명령(툴) 실행 요청 모델.
    
    사용 가능한 툴 중 하나를 선택하여 실행합니다.
    각 툴은 고유한 파라미터 스키마를 가지고 있습니다.
    
    Attributes:
        name: 실행할 툴의 이름
            가능한 값: "post_blog_article", "search_vector_db",
                      "search_graph_db"
        params: 툴별 파라미터 딕셔너리
    
    Example:
        >>> request = CommandExecuteRequest(
        ...     name="post_blog_article",
        ...     params={
        ...         "title": "My Article",
        ...         "markdown": "# Hello World"
        ...     }
        ... )
    """
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
    """명령 실행 결과 응답 모델.
    
    툴 실행의 성공 여부와 결과를 담습니다.
    
    Attributes:
        ok: 실행 성공 여부
        tool: 실행된 툴의 이름
        result: 툴 실행 결과 (툴마다 다른 형식)
            - post_blog_article: {"success": True, "article": {...}}
            - search_vector_db: {"matches": [...]}
            - search_graph_db: {"matches": [...]}
    
    Example:
        >>> result = CommandExecuteResult(
        ...     ok=True,
        ...     tool="post_blog_article",
        ...     result={"success": True, "article_id": "123"}
        ... )
    """
    ok: bool
    tool: str
    result: Any


class ToolSchema(BaseModel):
    """툴 스키마 정의 모델.
    
    사용 가능한 툴의 메타데이터를 표현합니다.
    LLM이나 클라이언트가 툴을 이해하고 올바르게 호출할 수 있도록 합니다.
    
    Attributes:
        name: 툴 식별자 (고유값)
        title: 사람이 읽을 수 있는 제목
        description: 툴의 기능 설명
        input_schema: JSON Schema 형식의 입력 파라미터 스키마
    
    Example:
        >>> tool = ToolSchema(
        ...     name="post_blog_article",
        ...     title="Post Blog Article",
        ...     description="Publish an article to the blog platform",
        ...     input_schema={
        ...         "type": "object",
        ...         "properties": {
        ...             "title": {"type": "string"},
        ...             "markdown": {"type": "string"}
        ...         },
        ...         "required": ["title", "markdown"]
        ...     }
        ... )
    """
    name: str
    title: str
    description: str
    input_schema: Dict[str, Any]


class CommandsListResponse(BaseModel):
    """사용 가능한 명령(툴) 목록 응답 모델.
    
    GET /api/v1/commands 엔드포인트의 응답으로 사용됩니다.
    
    Attributes:
        tools: 사용 가능한 모든 툴의 스키마 배열
    
    Example:
        >>> response = CommandsListResponse(
        ...     tools=[
        ...         ToolSchema(name="post_blog_article", ...),
        ...         ToolSchema(name="search_vector_db", ...)
        ...     ]
        ... )
    """
    tools: List[ToolSchema]