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
    LLMFinalArtifact,
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
    
    # 2. 시스템 프롬프트 구성 — 코드베이스 맥락 + 개인 블로그 초안(확인 후 게시)
    system_prompt = """당신은 사용자의 코드베이스와 요청을 바탕으로 개인 기술 블로그용 글 초안을 준비하는 기획 어시스턴트입니다.

제품 흐름(반드시 준수):
- 산출물은 항상 사용자가 검토할 마크다운(.md) 형태의 블로그 초안으로 이어지도록, 필요한 근거를 툴로 수집합니다.
- 실제 게시·업로드·발행 API 호출 등은 하지 않습니다. 초안만 제안합니다.

사용 가능한 툴:
- search_codebase: MongoDB에 인덱싱된 코드베이스 청크 검색 (파일 경로·내용 발췌)
- get_user_blog_posts: 사용자의 블로그 포스트 기록 조회 (톤·구조·태그 패턴 참고)

작업 지침:
1. 요청을 분석하고, 글 초안에 넣을 기술 근거·사용자 글 스타일이 필요한지 판단하세요.

2. 코드 위치, 구현, 버그·리팩터링, 아키텍처, "어디에 정의되나", "이 함수 역할" 등 저장소 근거가 필요하면
   search_codebase를 호출하세요. 코드 관련 주장은 추측보다 검색을 우선합니다.
   query에는 식별자·개념·파일명 일부 등 검색어를 넣으세요.

3. 블로그 톤·문장 리듬·제목/소제목 습관·태그 사용을 맞추려면 get_user_blog_posts를 호출하세요.
   블로그 글/포스트 작성 요청, "블로그", "글", "포스트", "게시 준비", "발행 전 초안" 등에 해당하면 특히 호출합니다.
   이 툴은 스타일 참고용이며, 여전히 게시는 사용자 확인 후입니다.

4. 기술 블로그 글이면 코드 근거와 스타일이 모두 도움이 될 때 두 툴을 함께 호출할 수 있습니다.
   코드가 글의 핵심이면 search_codebase를 먼저 호출하는 편이 좋습니다.

5. 저장소·기존 글 없이도 충분한 순수 잡담·일반 상식만 있으면 툴 없이 답할 수 있습니다.

중요: 초안 품질이 오르면 툴을 쓰는 것이 맞다고 판단되면 반드시 호출하고, 검색·조회 없이 코드 내용을 단정하지 마세요."""
    
    # 3. 사용자 메시지 구성
    context_str = json.dumps(context, ensure_ascii=False, indent=2) if context else "없음"
    user_message = f"""사용자 요청: {prompt}

추가 컨텍스트:
{context_str}

위 요청을 처리하기 위해 필요한 툴을 선택하세요. (최종 블로그용 .md 초안은 이어지는 단계에서 작성됩니다.)"""
    
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
            final_artifact = await _generate_final_response(
                request.prompt,
                executed_tool_calls,
                request.model,
                history=list(request.history),
            )
        except Exception as e:
            logger.error(f"Failed to generate final response from LLM: {e}")
            final_artifact = _fallback_final_artifact(successful_tools, failed_tools)
    else:
        final_artifact = _fallback_final_artifact(successful_tools, failed_tools)

    return LLMExecuteResult(
        ok=len(failed_tools) == 0,
        thought=thought,
        tool_calls=executed_tool_calls,
        final_response=final_artifact.blog_markdown,
        final_artifact=final_artifact,
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


def _parse_final_artifact(raw: Optional[str]) -> LLMFinalArtifact:
    """2차 LLM 응답 문자열을 JSON으로 파싱해 LLMFinalArtifact로 만듭니다. 실패 시 폴백."""
    if not raw or not raw.strip():
        return LLMFinalArtifact(
            answer="내용을 생성하지 못했습니다. 다시 시도해 주세요.",
            blog_markdown="# 초안\n\n내용을 생성하지 못했습니다. 다시 시도해 주세요.",
        )
    text = raw.strip()
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except (json.JSONDecodeError, ValueError):
        preview = text[:2000]
        return LLMFinalArtifact(
            answer=preview,
            blog_markdown=f"# 초안\n\n{preview}",
        )

    answer = str(
        data.get("answer")
        or data.get("direct_answer")
        or data.get("summary")
        or ""
    )
    blog_markdown = str(
        data.get("blog_markdown")
        or data.get("markdown")
        or data.get("blog_md")
        or ""
    )
    if not blog_markdown.strip() and answer.strip():
        blog_markdown = f"# 초안\n\n{answer.strip()}"
    if not answer.strip() and blog_markdown.strip():
        answer = "블로그 초안을 생성했습니다. 본문은 blog_markdown 필드를 확인하세요."

    return LLMFinalArtifact(
        answer=answer,
        blog_markdown=blog_markdown.strip()
        or "# 초안\n\n내용이 비어 있습니다.",
    )


async def _generate_final_response(
    original_prompt: str,
    tool_calls: list[ToolCall],
    model: str = None,
    history: Optional[List[ChatMessage]] = None,
) -> LLMFinalArtifact:
    """툴 실행 결과를 바탕으로 answer / blog_markdown JSON 산출 (Java가 동기 응답으로 파싱)."""

    history = history or []
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    _TOOL_RESULT_PREVIEW_LEN = 3000
    tool_results_summary = []
    for tc in tool_calls:
        status = "✅ 성공" if tc.success else "❌ 실패"
        raw = json.dumps(tc.result, ensure_ascii=False)
        preview = raw if len(raw) <= _TOOL_RESULT_PREVIEW_LEN else raw[:_TOOL_RESULT_PREVIEW_LEN] + "…(잘림)"
        tool_results_summary.append(f"{status} {tc.tool}: {preview}")

    summary_text = "\n".join(tool_results_summary) if tool_results_summary else "(툴 실행 없음 — 사용자 요청만 반영하세요.)"

    final_system = """당신은 개인 기술 블로그 초안과 사용자 응답을 함께 만드는 편집자입니다.

반드시 유효한 JSON 객체 하나만 출력하세요. 앞뒤 설명 문장이나 마크다운 코드펜스(```)를 붙이지 마세요.

필수 키(정확히 이 두 개만 사용):
- "answer": 문자열. 사용자 질의에 대한 직접 답·요약(채팅용). 블로그 글 전체는 넣지 않음.
- "blog_markdown": 문자열. .md로 저장할 블로그 초안 전체. 첫 줄은 `# 제목`. `##` 소제목, 코드는 ```언어 ... ```. 끝에 `태그: a, b` 한 줄 권장.

추론·계획 과정은 출력에 포함하지 마세요. 내부적으로 요청과 툴 결과를 모두 반영해 answer와 blog_markdown만 작성하세요.

규칙:
- 실제 게시·업로드·발행했다는 표현 금지. 초안이며 사용자 확인 후 게시임을 answer에 짧게 언급 가능.
- JSON 문자열 값의 줄바꿈·따옴표는 JSON 이스케이프를 따르세요."""

    final_user_content = f"""사용자 요청:
{original_prompt}

수집된 정보(툴 결과):
{summary_text}

위 내용을 반영해 반드시 아래 형식의 JSON만 출력하세요:
{{"answer":"...","blog_markdown":"..."}}

blog_markdown 작성 시:
- search_codebase 결과가 있으면 경로·발췌를 녹이고, 실패한 툴이 있으면 한계를 짧게 밝힘.
- get_user_blog_posts가 있으면 톤·제목·태그 습관을 맞춤.
언어: 기본 한국어."""

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": final_system},
    ]
    messages.extend(_history_to_openai_messages(history))
    messages.append({"role": "user", "content": final_user_content})

    response = await client.chat.completions.create(
        model=model or settings.DEFAULT_LLM_MODEL,
        messages=messages,
        temperature=0.7,
        max_tokens=settings.LLM_MAX_TOKENS,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    return _parse_final_artifact(content)


def _create_fallback_response(successful_tools: list[str], failed_tools: list[str]) -> str:
    """Create fallback human message when LLM is unavailable."""
    if failed_tools:
        return (
            f"일부 작업을 완료했습니다. "
            f"성공: {', '.join(successful_tools) if successful_tools else '없음'}, "
            f"실패: {', '.join(failed_tools)}"
        )
    return (
        f"요청하신 작업을 모두 완료했습니다. "
        f"실행된 작업: {', '.join(successful_tools) if successful_tools else '없음'}"
    )


def _fallback_final_artifact(
    successful_tools: list[str], failed_tools: list[str]
) -> LLMFinalArtifact:
    """LLM 불가 시에도 Java가 동일 스키마로 파싱할 수 있게 합니다."""
    msg = _create_fallback_response(successful_tools, failed_tools)
    return LLMFinalArtifact(
        answer=msg,
        blog_markdown=f"# 초안\n\n{msg}\n\n태그: clog, 상태",
    )

