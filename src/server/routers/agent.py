"""LLM agent endpoints for natural language command execution."""
from fastapi import APIRouter, Depends, HTTPException, status
from src.server.deps import verify_api_key
from src.server.schemas import (
    LLMExecuteRequest,
    LLMExecuteResult,
    ToolCall
)
from src.server.routers.commands import TOOLS_REGISTRY
import logging

router = APIRouter(prefix="/api/v1/llm", tags=["llm-agent"])
logger = logging.getLogger(__name__)


async def execute_tool_by_name(tool_name: str, params: dict) -> dict:
    """Execute a tool by name with given parameters.
    
    Args:
        tool_name: Name of the tool to execute
        params: Parameters for the tool
        
    Returns:
        Tool execution result
        
    Raises:
        Exception: If tool not found or execution fails
    """
    if tool_name not in TOOLS_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found")
    
    tool_module = TOOLS_REGISTRY[tool_name]
    if not hasattr(tool_module, "run"):
        raise ValueError(f"Tool '{tool_name}' has no run method")
    
    return await tool_module.run(params)


async def call_llm_with_tools(
    prompt: str,
    context: dict,
    available_tools: list,
    model: str = None
) -> tuple[str, list[dict]]:
    """Call LLM with available tools and get tool calls.
    
    이 함수는 실제 LLM API 호출을 시뮬레이션합니다.
    실제 구현 시에는 Anthropic, OpenAI 등의 API를 호출해야 합니다.
    
    Args:
        prompt: User's natural language command
        context: Additional context
        available_tools: List of available tool schemas
        model: LLM model to use
        
    Returns:
        Tuple of (thought_process, tool_calls_to_make)
    """
    # DUMMY IMPLEMENTATION
    # 실제로는 여기서 LLM API를 호출합니다:
    # - Anthropic Claude API (messages API with tools)
    # - OpenAI GPT API (chat completions with function calling)
    
    logger.info(f"LLM called with prompt: {prompt}")
    logger.info(f"Available tools: {[t['name'] for t in available_tools]}")
    logger.info(f"Context keys: {list(context.keys())}")
    
    # 더미 응답: 프롬프트 키워드 기반으로 툴 선택
    thought = "사용자의 요청을 분석하여 적절한 툴을 선택합니다."
    tool_calls = []
    
    prompt_lower = prompt.lower()
    
    # 키워드 기반 더미 로직
    if "인덱스" in prompt_lower or "index" in prompt_lower:
        if "diff" in context or "files" in context:
            tool_calls.append({
                "tool": "update_code_index",
                "params": {
                    "files": context.get("diff", {}).get("files", [])
                }
            })
    
    if "블로그" in prompt_lower or "blog" in prompt_lower or "글" in prompt_lower:
        tool_calls.append({
            "tool": "post_blog_article",
            "params": {
                "title": "자동 생성된 글",
                "markdown": f"# 코드 변경 요약\n\n{prompt}"
            }
        })
    
    if "노션" in prompt_lower or "notion" in prompt_lower:
        tool_calls.append({
            "tool": "publish_to_notion",
            "params": {
                "title": "자동 생성 페이지",
                "content": prompt
            }
        })
    
    if "커밋" in prompt_lower or "commit" in prompt_lower or "push" in prompt_lower:
        tool_calls.append({
            "tool": "create_commit_and_push",
            "params": {
                "repo_path": context.get("repo_path", "."),
                "files": context.get("files", []),
                "commit_message": "Auto commit"
            }
        })
    
    # 아무 툴도 선택되지 않은 경우 기본 응답
    if not tool_calls:
        tool_calls.append({
            "tool": "refresh_rag_indexes",
            "params": {"full_rebuild": False}
        })
    
    return thought, tool_calls


@router.post("/execute", response_model=LLMExecuteResult)
async def execute_llm_command(
    request: LLMExecuteRequest,
    api_key: str = Depends(verify_api_key)
) -> LLMExecuteResult:
    """사용자의 자연어 명령을 LLM이 해석하고 실행합니다.
    
    이 엔드포인트는 다음 과정을 거칩니다:
    1. 사용자의 자연어 명령을 받음
    2. LLM에게 명령과 사용 가능한 툴 목록을 전달
    3. LLM이 어떤 툴을 어떤 순서로 실행할지 결정
    4. 선택된 툴들을 순차적으로 실행
    5. 각 툴의 결과를 LLM에게 피드백
    6. LLM의 최종 응답을 사용자에게 반환
    
    Args:
        request: LLM 실행 요청 (프롬프트, 컨텍스트 등)
        api_key: 인증된 API 키
        
    Returns:
        LLM 실행 결과 (사고 과정, 툴 호출 목록, 최종 응답)
        
    Raises:
        HTTPException: 400 if invalid request, 500 if execution fails
    """
    logger.info(f"LLM execute request: {request.prompt}")
    
    try:
        # 1. 사용 가능한 툴 목록 가져오기
        available_tools = []
        for tool_name, tool_module in TOOLS_REGISTRY.items():
            if hasattr(tool_module, "TOOL"):
                available_tools.append(tool_module.TOOL)
        
        # 2. LLM 호출하여 실행할 툴 결정
        thought, tool_calls_to_make = await call_llm_with_tools(
            prompt=request.prompt,
            context=request.context,
            available_tools=available_tools,
            model=request.model
        )
        
        # 3. 선택된 툴들을 순차적으로 실행
        executed_tool_calls = []
        for tool_call_plan in tool_calls_to_make:
            tool_name = tool_call_plan["tool"]
            params = tool_call_plan["params"]
            
            try:
                result = await execute_tool_by_name(tool_name, params)
                executed_tool_calls.append(ToolCall(
                    tool=tool_name,
                    params=params,
                    result=result,
                    success=True
                ))
                logger.info(f"Successfully executed tool: {tool_name}")
            except Exception as e:
                logger.error(f"Failed to execute tool {tool_name}: {e}")
                executed_tool_calls.append(ToolCall(
                    tool=tool_name,
                    params=params,
                    result={"error": str(e)},
                    success=False
                ))
        
        # 4. 최종 응답 생성
        # 실제로는 툴 실행 결과를 다시 LLM에게 전달하여 최종 응답 생성
        successful_tools = [tc.tool for tc in executed_tool_calls if tc.success]
        failed_tools = [tc.tool for tc in executed_tool_calls if not tc.success]
        
        if failed_tools:
            final_response = (
                f"일부 작업을 완료했습니다. "
                f"성공: {', '.join(successful_tools) if successful_tools else '없음'}, "
                f"실패: {', '.join(failed_tools)}"
            )
        else:
            final_response = (
                f"요청하신 작업을 모두 완료했습니다. "
                f"실행된 작업: {', '.join(successful_tools)}"
            )
        
        return LLMExecuteResult(
            ok=len(failed_tools) == 0,
            thought=thought,
            tool_calls=executed_tool_calls,
            final_response=final_response,
            model_used=request.model or "dummy-model"
        )
        
    except Exception as e:
        logger.error(f"Error executing LLM command: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute LLM command: {str(e)}"
        )

