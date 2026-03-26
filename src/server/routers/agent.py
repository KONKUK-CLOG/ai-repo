"""LLM agent endpoints for natural language command execution."""
import asyncio
import json
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
# from src.server.deps import get_current_user  # 주석 처리: TS 직접 통신 시 사용했던 함수. 현재는 Java 서버를 통해 내부 통신하므로 사용하지 않음
# from src.models.user import User  # 주석 처리: JWT 인증이 필요 없으므로 User 모델 사용하지 않음
from src.server.schemas import (
    ChatMessage,
    LLMExecuteRequest,
    LLMExecuteResult,
    ToolCall,
)
from src.server.settings import settings
from src.mcp.tools import (
    get_user_blog_posts,
    search_codebase_mongo,
    # 주석 처리: RAG 관련 툴은 다음 학기 구현 예정
    # search_vector_db,
    # search_graph_db
)

router = APIRouter(prefix="/internal/v1/llm", tags=["llm-agent"])
logger = logging.getLogger(__name__)

# ============================================================================
# 툴 레지스트리 (Tool Registry)
# ============================================================================

# 사용 가능한 모든 툴의 중앙 레지스트리
# agent.py와 commands.py에서 공유하여 사용
TOOLS_REGISTRY = {
    "get_user_blog_posts": get_user_blog_posts,
    "search_codebase": search_codebase_mongo,
    # 주석 처리: RAG 관련 툴은 다음 학기 구현 예정
    # "search_vector_db": search_vector_db,
    # "search_graph_db": search_graph_db,
}


def _history_to_openai_messages(history: List[ChatMessage]) -> List[Dict[str, str]]:
    """Java가 보낸 히스토리를 OpenAI messages 항목으로 변환합니다."""
    return [{"role": m.role, "content": m.content} for m in history]


def _format_sse(event: str, data: Dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _llm_result_to_dict(result: LLMExecuteResult) -> Dict[str, Any]:
    return json.loads(result.model_dump_json())


ProgressCallback = Optional[Callable[[Dict[str, Any]], Awaitable[None]]]


async def _execute_regular_tool(tool_name: str, params: dict, user_api_key: str | None = None) -> dict:
    """Execute a regular tool by name with given parameters.
    
    Args:
        tool_name: Name of the tool to execute
        params: Parameters for the tool
        user_api_key: 사용자 API 키 (현재는 사용하지 않음, settings에서 가져옴)
        
    Returns:
        Tool execution result
        
    Raises:
        Exception: If tool not found or execution fails
    """
    if tool_name not in TOOLS_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found")
    
    tool_module = TOOLS_REGISTRY[tool_name]
    effective_params = dict(params or {})
    
    if not hasattr(tool_module, "run"):
        raise ValueError(f"Tool '{tool_name}' has no run method")
    
    return await tool_module.run(effective_params)


async def call_llm_with_tools(
    prompt: str,
    context: dict,
    available_tools: list,
    model: str = None,
    history: Optional[List[ChatMessage]] = None,
) -> tuple[str, list[dict]]:
    """Call OpenAI GPT with available tools and get tool calls.
    
    OpenAI GPT API를 호출하여 사용자의 자연어 명령을 분석하고
    적절한 툴을 선택합니다.
    
    Args:
        prompt: User's natural language command
        context: Additional context
        available_tools: List of available tool schemas
        model: LLM model to use
        history: 이전 대화 턴 (Java NoSQL 등에서 전달)
        
    Returns:
        Tuple of (thought_process, tool_calls_to_make)
    """
    history = history or []
    logger.info(f"LLM called with prompt: {prompt}")
    logger.info(f"Available tools: {[t['name'] for t in available_tools]}")
    logger.info(f"Context keys: {list(context.keys())}")
    logger.info(f"History turns: {len(history)}")
    
    # API 키 확인
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set - using fallback dummy logic")
        return _fallback_tool_selection(prompt, context)
    
    # 1. OpenAI 클라이언트 생성
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    # 2. 시스템 프롬프트 구성
    system_prompt = """당신은 사용자의 요청을 분석하고 적절히 응답하는 AI 어시스턴트입니다.

사용 가능한 툴:
- search_codebase: MongoDB에 인덱싱된 코드베이스 청크 검색 (파일 경로·내용 발췌)
- get_user_blog_posts: 사용자의 블로그 포스트 기록 조회

작업 지침:
1. 요청을 먼저 분석하세요.

2. 코드 위치, 구현 방식, 버그 원인, 리팩터링, 아키텍처, "어디에 정의되어 있나", "이 함수가 뭐 하는지" 등
   저장소에 근거한 답변이 필요하면 search_codebase를 호출하세요. 코드 관련 질문에서는 추측보다 검색을 우선하세요.
   search_codebase의 query에는 찾고 싶은 식별자·개념·파일 이름 일부 등을 넣으세요.

3. 블로그 글 작성·스타일·톤·태그 패턴이 필요하면 get_user_blog_posts를 호출하세요.
   다음에 해당하면 블로그 툴을 쓰세요:
   - 블로그 글/포스트/발행 요청, "블로그", "글", "포스트", "게시", "발행" 등
   - 사용자 기존 글 스타일·주제·태그를 맞춰야 할 때
   get_user_blog_posts 호출 후: 톤·구조·태그를 파악하고 마크다운 초안만 제안 (게시는 하지 않음).

4. 코드와 블로그가 모두 필요하면 두 툴을 모두 호출할 수 있습니다. 순서는 요청에 맞게 정하되,
   코드 근거가 핵심이면 search_codebase를 먼저 호출하는 것이 좋습니다.

5. 단순 잡담·일반 상식 등 저장소/블로그가 불필요하면 툴 없이 직접 답변하세요.

블로그 초안 작성 시: 제목·본문·태그는 사용자 기존 패턴을 참고하세요.

중요: 저장소나 블로그를 쓰면 품질이 올라간다고 판단되면 반드시 해당 툴을 호출하고, 근거 없이 단정하지 마세요."""
    
    # 3. 사용자 메시지 구성
    context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "없음"
    user_message = f"""사용자 요청: {prompt}

추가 컨텍스트:
{context_str}

위 요청을 처리하기 위해 필요한 툴을 선택하고 실행하세요."""
    
    # 4. 툴 스키마를 OpenAI 형식으로 변환
    openai_tools = []
    for tool in available_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {})
            }
        })
    
    # 5. LLM 호출: [system] + [히스토리] + [이번 턴 user 메시지]
    messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(_history_to_openai_messages(history))
    messages.append({"role": "user", "content": user_message})

    try:
        response = await client.chat.completions.create(
            model=model or settings.DEFAULT_LLM_MODEL,
            messages=messages,
            tools=openai_tools,
            tool_choice="auto",
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        
        logger.info(f"LLM response received from {response.model}")
        
        # 6. 응답 파싱
        message = response.choices[0].message
        thought = message.content or "툴 실행을 시작합니다."
        tool_calls = []
        
        if message.tool_calls:
            for tool_call in message.tool_calls:
                try:
                    params = json.loads(tool_call.function.arguments)
                    tool_calls.append({
                        "tool": tool_call.function.name,
                        "params": params
                    })
                    logger.info(f"Tool selected: {tool_call.function.name}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse tool arguments: {e}")
                    continue
        
        # 툴이 선택되지 않은 경우
        if not tool_calls:
            logger.warning("LLM did not select any tools")
            thought = thought or "요청을 처리할 적절한 툴을 찾지 못했습니다."
        
        return thought, tool_calls
        
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        # 폴백: 더미 로직 사용
        return _fallback_tool_selection(prompt, context)


def _fallback_tool_selection(prompt: str, context: dict) -> tuple[str, list[dict]]:
    """Fallback tool selection when LLM API is unavailable.
    
    API 키가 없거나 LLM 호출이 실패한 경우 사용되는 키워드 기반 폴백 로직.
    """
    logger.info("Using fallback keyword-based tool selection")
    thought = "LLM API를 사용할 수 없어 키워드 기반 매칭을 사용합니다."
    tool_calls = []
    
    prompt_lower = prompt.lower()
    
    # 키워드 기반 더미 로직
    # 블로그 관련 키워드가 있으면 get_user_blog_posts를 호출하도록 하지 않음
    # (user_id가 필요하므로 fallback에서는 툴을 호출하지 않고 직접 응답)
    # 블로그 글 작성 요청이 있으면 마크다운 형식으로 직접 응답 생성
    
    
    
    # 아무 툴도 선택되지 않은 경우
    if not tool_calls:
        thought = "요청을 처리할 적절한 툴을 찾지 못했습니다. 구체적인 작업을 명시해주세요."
    
    return thought, tool_calls


async def run_llm_execute_pipeline(
    request: LLMExecuteRequest,
    progress: ProgressCallback = None,
) -> LLMExecuteResult:
    """LLM 실행 전 과정(툴 계획 → 실행 → 최종 응답). SSE 등에서 progress 콜백으로 단계 전달."""

    async def emit(payload: Dict[str, Any]) -> None:
        if progress:
            await progress(payload)

    await emit({"phase": "started", "message": "요청 처리 시작"})

    logger.info(f"LLM execute request: {request.prompt}")

    available_tools = []
    for _, tool_module in TOOLS_REGISTRY.items():
        if hasattr(tool_module, "TOOL"):
            available_tools.append(tool_module.TOOL)

    await emit({"phase": "llm_planning", "message": "툴 선택을 위해 LLM 호출 중"})

    thought, tool_calls_to_make = await call_llm_with_tools(
        prompt=request.prompt,
        context=request.context,
        available_tools=available_tools,
        model=request.model,
        history=list(request.history),
    )

    tool_names_planned = [tc["tool"] for tc in tool_calls_to_make]
    await emit(
        {
            "phase": "llm_planning_done",
            "message": "LLM 툴 계획 완료",
            "tools": tool_names_planned,
        }
    )

    async def _run_one_tool(tool_call_plan: dict) -> ToolCall:
        tool_name = tool_call_plan["tool"]
        params = dict(tool_call_plan["params"])
        if tool_name in ("get_user_blog_posts", "search_codebase"):
            params["user_id"] = request.user_id
        try:
            result = await _execute_regular_tool(
                tool_name,
                params,
                user_api_key=None,
            )
            logger.info(f"Successfully executed tool: {tool_name}")
            return ToolCall(
                tool=tool_name,
                params=params,
                result=result,
                success=True,
            )
        except Exception as e:
            logger.error(f"Failed to execute tool {tool_name}: {e}")
            return ToolCall(
                tool=tool_name,
                params=params,
                result={"error": str(e)},
                success=False,
            )

    for tool_call_plan in tool_calls_to_make:
        tool_name = tool_call_plan["tool"]
        await emit(
            {
                "phase": "tool_running",
                "tool": tool_name,
                "message": f"{tool_name} 실행 중",
            }
        )

    if tool_calls_to_make:
        executed_tool_calls = await asyncio.gather(
            *[_run_one_tool(p) for p in tool_calls_to_make]
        )
    else:
        executed_tool_calls = []

    for tc in executed_tool_calls:
        done_msg = (
            f"{tc.tool} 완료"
            if tc.success
            else (
                str(tc.result.get("error", "failed"))
                if isinstance(tc.result, dict)
                else str(tc.result)
            )
        )
        await emit(
            {
                "phase": "tool_done",
                "tool": tc.tool,
                "success": tc.success,
                "message": done_msg,
            }
        )

    successful_tools = [tc.tool for tc in executed_tool_calls if tc.success]
    failed_tools = [tc.tool for tc in executed_tool_calls if not tc.success]

    await emit({"phase": "generating_final", "message": "최종 응답 생성 중"})

    if settings.OPENAI_API_KEY:
        try:
            final_response = await _generate_final_response(
                request.prompt,
                executed_tool_calls,
                request.model,
                history=list(request.history),
            )
        except Exception as e:
            logger.error(f"Failed to generate final response from LLM: {e}")
            final_response = _create_fallback_response(successful_tools, failed_tools)
    else:
        final_response = _create_fallback_response(successful_tools, failed_tools)

    return LLMExecuteResult(
        ok=len(failed_tools) == 0,
        thought=thought,
        tool_calls=executed_tool_calls,
        final_response=final_response,
        model_used=request.model or settings.DEFAULT_LLM_MODEL,
    )


@router.post("/execute", response_model=LLMExecuteResult)
async def execute_llm_command(
    request: LLMExecuteRequest,
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
        request: LLM 실행 요청 (user_id, 프롬프트, 컨텍스트 등)
        
    Returns:
        LLM 실행 결과 (사고 과정, 툴 호출 목록, 최종 응답)
        
    Raises:
        HTTPException: 400 if invalid request, 500 if execution fails
    """
    try:
        return await run_llm_execute_pipeline(request)
    except Exception as e:
        logger.error(f"Error executing LLM command: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute LLM command: {str(e)}",
        )


@router.post("/execute/stream")
async def execute_llm_command_stream(request: LLMExecuteRequest) -> StreamingResponse:
    """동일 본문으로 LLM 실행; 진행 단계는 SSE(`event: progress`), 완료 시 `event: complete`.

    페이로드는 JSON이며 `phase`로 단계를 구분합니다:
    started, llm_planning, llm_planning_done, tool_running, tool_done, generating_final,
    오류 시 `event: error`.
    """

    async def event_gen():
        queue: asyncio.Queue = asyncio.Queue()

        async def progress(payload: Dict[str, Any]) -> None:
            await queue.put(_format_sse("progress", payload))

        async def runner() -> None:
            try:
                result = await run_llm_execute_pipeline(request, progress=progress)
                await queue.put(_format_sse("complete", _llm_result_to_dict(result)))
            except Exception as e:
                logger.exception("Stream LLM execute failed")
                await queue.put(
                    _format_sse(
                        "error",
                        {"phase": "error", "message": str(e)},
                    )
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            await task

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _generate_final_response(
    original_prompt: str,
    tool_calls: list[ToolCall],
    model: str = None,
    history: Optional[List[ChatMessage]] = None,
) -> str:
    """Generate final user-friendly response using LLM.
    
    툴 실행 결과를 LLM에게 전달하여 사용자 친화적인 최종 응답을 생성합니다.
    """
    history = history or []
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    # 툴 실행 결과 요약
    tool_results_summary = []
    for tc in tool_calls:
        status = "✅ 성공" if tc.success else "❌ 실패"
        tool_results_summary.append(
            f"{status} {tc.tool}: {json.dumps(tc.result, ensure_ascii=False)[:200]}"
        )
    
    summary_text = "\n".join(tool_results_summary)
    
    final_user_content = f"""사용자 요청: {original_prompt}

실행된 작업 결과:
{summary_text}

위 결과를 바탕으로 사용자에게 친절하고 명확한 최종 응답을 한국어로 작성해주세요.
간결하게 2-3문장으로 요약해주세요."""

    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": "당신은 작업 결과를 사용자에게 친절하고 명확하게 전달하는 어시스턴트입니다."
        }
    ]
    messages.extend(_history_to_openai_messages(history))
    messages.append({"role": "user", "content": final_user_content})

    response = await client.chat.completions.create(
        model=model or settings.DEFAULT_LLM_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=500
    )
    
    return response.choices[0].message.content or "작업이 완료되었습니다."


def _create_fallback_response(successful_tools: list[str], failed_tools: list[str]) -> str:
    """Create fallback response when LLM is unavailable."""
    if failed_tools:
        return (
            f"일부 작업을 완료했습니다. "
            f"성공: {', '.join(successful_tools) if successful_tools else '없음'}, "
            f"실패: {', '.join(failed_tools)}"
        )
    else:
        return (
            f"요청하신 작업을 모두 완료했습니다. "
            f"실행된 작업: {', '.join(successful_tools)}"
        )

