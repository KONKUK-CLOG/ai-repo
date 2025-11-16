"""Command execution endpoints (개발 전용).

⚠️  이 모듈은 개발/디버깅 용도로만 사용됩니다.
프로덕션에서는 ENABLE_DIRECT_TOOLS=false로 설정하여 비활성화하세요.

이 모듈은 툴을 직접 지정하여 실행하는 엔드포인트를 제공합니다.
agent.py와 달리 LLM이 개입하지 않으며, 개발자가 이미 어떤 툴을 실행할지 결정한 상태입니다.

사용 케이스:
- 개발 환경에서 툴 단독 테스트
- LLM 없이 툴 동작 확인
- 디버깅 및 개발 편의성

엔드포인트:
- GET /api/v1/commands: 사용 가능한 툴 목록 및 스키마 조회
- POST /api/v1/commands/execute: 지정된 툴 실행

차이점:
- commands.py: 개발자가 툴 이름을 명시적으로 지정 (개발 전용)
- agent.py: LLM이 자연어 명령을 분석하여 툴 자동 선택 (프로덕션)
"""
from fastapi import APIRouter, Depends, HTTPException, Header, status
from typing import Optional
from src.server.deps import get_current_user
from src.models.user import User
from src.server.schemas import (
    CommandExecuteRequest,
    CommandExecuteResult,
    CommandsListResponse,
    ToolSchema,
    ErrorResponse,
    ErrorDetail
)
from src.server.routers.agent import TOOLS_REGISTRY
import logging
import uuid

router = APIRouter(prefix="/api/v1/commands", tags=["commands (dev only)"])
logger = logging.getLogger(__name__)


@router.get("", response_model=CommandsListResponse)
async def list_commands(
    user: User = Depends(get_current_user)
) -> CommandsListResponse:
    """사용 가능한 모든 툴의 메타데이터를 조회합니다.
    
    이 엔드포인트는 다음 용도로 사용됩니다:
    1. TS 클라이언트가 UI를 동적으로 구성
    2. LLM이 사용 가능한 툴을 파악
    3. API 문서 자동 생성
    
    각 툴의 스키마에는 다음 정보가 포함됩니다:
    - name: 툴 식별자
    - title: 사람이 읽을 수 있는 제목
    - description: 툴의 기능 설명
    - input_schema: JSON Schema 형식의 입력 파라미터 스키마
    
    Args:
        user: 인증된 사용자 (헤더에서 자동 추출 및 검증)
        
    Returns:
        사용 가능한 모든 툴의 스키마 목록
        
    Example:
        >>> GET /api/v1/commands
        >>> Headers: {"x-api-key": "user-api-key"}
        >>> Response:
        {
            "tools": [
                {
                    "name": "post_blog_article",
                    "title": "Post Blog Article",
                    "description": "Publish an article to the blog platform",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "markdown": {"type": "string"}
                        },
                        "required": ["title", "markdown"]
                    }
                },
                ...
            ]
        }
    """
    tools = []
    
    # 레지스트리에 등록된 모든 툴 순회
    for tool_name, tool_module in TOOLS_REGISTRY.items():
        # 각 툴 모듈에는 TOOL 딕셔너리가 정의되어 있음
        if hasattr(tool_module, "TOOL"):
            tool_def = tool_module.TOOL
            
            # 툴 스키마 객체 생성
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
    user: User = Depends(get_current_user),
    x_idempotency_key: Optional[str] = Header(None),
    x_api_key: str = Header(..., alias="x-api-key"),
) -> CommandExecuteResult:
    """지정된 툴을 실행합니다.
    
    사용자(또는 TS 클라이언트)가 이미 어떤 툴을 실행할지 결정한 상태에서 호출합니다.
    LLM이 개입하지 않으며, 툴 이름과 파라미터를 직접 지정합니다.
    
    처리 과정:
    1. Idempotency Key 생성 또는 사용 (중복 실행 방지)
    2. 툴 존재 여부 확인
    3. 툴 실행 (await tool.run(params))
    4. 결과 반환 또는 에러 처리
    
    Idempotency Key:
    - 헤더에 x-idempotency-key가 있으면 사용
    - 없으면 UUID 자동 생성
    - 동일한 키로 여러 번 호출해도 한 번만 실행되도록 보장 (추후 구현 가능)
    - 요청 추적 및 디버깅에 활용
    
    Args:
        request: 툴 실행 요청
            - name: 실행할 툴 이름 (예: "post_blog_article")
            - params: 툴별 파라미터 딕셔너리
        api_key: 검증된 API 키 (헤더에서 자동 추출 및 검증)
        x_idempotency_key: 선택적 Idempotency Key (중복 방지용)
        
    Returns:
        툴 실행 결과
        - ok: 성공 여부
        - tool: 실행된 툴 이름
        - result: 툴별 실행 결과 (형식은 툴마다 다름)
        
    Raises:
        HTTPException: 
            - 400: 툴이 존재하지 않음
            - 500: 툴 실행 중 에러 발생
    
    Example (성공):
        >>> POST /api/v1/commands/execute
        >>> Headers: {
        >>>     "x-api-key": "user-api-key",
        >>>     "x-idempotency-key": "abc-123"
        >>> }
        >>> Body: {
        >>>     "name": "post_blog_article",
        >>>     "params": {
        >>>         "title": "FastAPI 시작하기",
        >>>         "markdown": "# FastAPI\\n\\n빠르고 현대적인 웹 프레임워크"
        >>>     }
        >>> }
        >>> Response: {
        >>>     "ok": true,
        >>>     "tool": "post_blog_article",
        >>>     "result": {
        >>>         "success": true,
        >>>         "article": {
        >>>             "article_id": "123",
        >>>             "url": "https://...",
        >>>             "published": true
        >>>         }
        >>>     }
        >>> }
    
    Example (툴 없음):
        >>> Body: {"name": "invalid_tool", "params": {}}
        >>> Response (400): {
        >>>     "detail": "Tool 'invalid_tool' not found"
        >>> }
    """
    # 1. Idempotency Key 생성 또는 사용
    # 헤더에 키가 있으면 사용, 없으면 UUID 자동 생성
    idempotency_key = x_idempotency_key or str(uuid.uuid4())
    logger.info(f"Executing command '{request.name}' with idempotency key: {idempotency_key}")
    
    # 2. 툴 존재 여부 확인
    if request.name not in TOOLS_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tool '{request.name}' not found"
        )
    
    # 3. 레지스트리에서 툴 모듈 가져오기
    tool_module = TOOLS_REGISTRY[request.name]
    
    try:
        # 4. 툴 실행
        if hasattr(tool_module, "run"):
            # 툴의 run() 메서드 호출 (비동기)
            params = dict(request.params or {})

            if request.name == "post_blog_article":
                params.setdefault("api_key", x_api_key)

            result = await tool_module.run(params)
            
            # 성공 결과 반환
            return CommandExecuteResult(
                ok=True,
                tool=request.name,
                result=result
            )
        else:
            # 툴 모듈에 run 메서드가 없는 경우 (개발 오류)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Tool '{request.name}' has no run method"
            )
            
    except HTTPException:
        # HTTPException은 그대로 재발생 (이미 적절한 상태 코드와 메시지 포함)
        raise
    except Exception as e:
        # 그 외 예외는 500 에러로 변환
        logger.error(f"Error executing command '{request.name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": {
                    "type": type(e).__name__,        # 예외 타입
                    "message": str(e),               # 에러 메시지
                    "code": "EXECUTION_ERROR",       # 에러 코드
                    "request_id": idempotency_key    # 요청 추적용 ID
                }
            }
        )

