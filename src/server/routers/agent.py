"""LLM agent endpoints for natural language command execution."""
from fastapi import APIRouter, HTTPException, status
# from src.server.deps import get_current_user  # 주석 처리: TS 직접 통신 시 사용했던 함수. 현재는 Java 서버를 통해 내부 통신하므로 사용하지 않음
# from src.models.user import User  # 주석 처리: JWT 인증이 필요 없으므로 User 모델 사용하지 않음
from src.server.schemas import (
    LLMExecuteRequest,
    LLMExecuteResult,
    ToolCall
)
from src.server.settings import settings
from openai import AsyncOpenAI
from src.mcp.tools import (
    get_user_blog_posts,
    # 주석 처리: RAG 관련 툴은 다음 학기 구현 예정
    # search_vector_db,
    # search_graph_db
)
import logging
import json

router = APIRouter(prefix="/internal/v1/llm", tags=["llm-agent"])
logger = logging.getLogger(__name__)

# ============================================================================
# 툴 레지스트리 (Tool Registry)
# ============================================================================

# 사용 가능한 모든 툴의 중앙 레지스트리
# agent.py와 commands.py에서 공유하여 사용
TOOLS_REGISTRY = {
    "get_user_blog_posts": get_user_blog_posts,       # 사용자 블로그 포스트 조회
    # 주석 처리: RAG 관련 툴은 다음 학기 구현 예정
    # "search_vector_db": search_vector_db,             # Vector DB 의미론적 검색
    # "search_graph_db": search_graph_db,               # Graph DB 구조적 검색
}


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
    model: str = None
) -> tuple[str, list[dict]]:
    """Call OpenAI GPT with available tools and get tool calls.
    
    OpenAI GPT API를 호출하여 사용자의 자연어 명령을 분석하고
    적절한 툴을 선택합니다.
    
    Args:
        prompt: User's natural language command
        context: Additional context
        available_tools: List of available tool schemas
        model: LLM model to use
        
    Returns:
        Tuple of (thought_process, tool_calls_to_make)
    """
    logger.info(f"LLM called with prompt: {prompt}")
    logger.info(f"Available tools: {[t['name'] for t in available_tools]}")
    logger.info(f"Context keys: {list(context.keys())}")
    
    # API 키 확인
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set - using fallback dummy logic")
        return _fallback_tool_selection(prompt, context)
    
    # 1. OpenAI 클라이언트 생성
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    # 2. 시스템 프롬프트 구성
    system_prompt = """당신은 사용자의 요청을 분석하고 적절히 응답하는 AI 어시스턴트입니다.

사용 가능한 툴:
- get_user_blog_posts: 사용자의 블로그 포스트 기록 조회

작업 지침:
1. 사용자의 요청을 먼저 분석하세요.
2. 사용자의 블로그 글을 참고해야 한다고 판단되는 경우, 반드시 먼저 get_user_blog_posts 툴을 호출하세요.
   
   다음 상황에서는 반드시 get_user_blog_posts 툴을 먼저 호출해야 합니다:
   - 블로그 글 작성, 포스트 작성, 글 발행 등의 요청이 있을 때
   - 사용자의 기존 블로그 스타일, 톤, 주제를 맞춰야 할 때
   - 사용자의 블로그 태그 패턴이나 글쓰기 방식을 참고해야 할 때
   - 사용자의 블로그 기록을 바탕으로 더 나은 답변을 제공해야 할 때
   - "블로그", "글", "포스트", "게시", "발행" 등의 키워드가 포함된 요청일 때
   
   get_user_blog_posts 툴 호출 후:
   - 사용자의 글쓰기 스타일, 주제, 태그 사용 패턴 등을 분석하세요.
   - 사용자의 기존 블로그 포스트의 톤, 구조, 형식을 파악하세요.
   - 이를 바탕으로 사용자에게 맞는 블로그 글을 마크다운 형식으로 작성하세요.
   - 블로그 글은 게시하지 않고, 마크다운 형식의 초안만 사용자에게 제공하세요.

3. 블로그와 관련 없는 단순 질문이나 정보 요청의 경우, 툴을 사용하지 않고 직접 답변하세요.

블로그 글 작성 시 고려사항:
- 제목(title): 명확하고 매력적인 제목 (사용자의 기존 제목 스타일 참고)
- 내용(markdown): 마크다운 형식으로 구조화된 글 (사용자의 기존 글 구조 참고)
- 태그(tags): 사용자의 기존 블로그 포스트에서 사용한 태그 패턴을 반드시 참고하여 제안
- 톤과 스타일: 사용자의 기존 글쓰기 스타일과 톤을 정확히 유지하세요.

중요: 사용자의 블로그 기록을 참고하면 더 나은 답변을 제공할 수 있다고 판단되면, 반드시 get_user_blog_posts 툴을 먼저 호출하세요. 툴 호출 없이 추측으로 답변하지 마세요.

입력된 내용과 사용자의 블로그 기록을 기반으로 답변을 생성하며, 외부 코드베이스 검색은 수행하지 않습니다."""
    
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
    
    # 5. LLM 호출
    try:
        response = await client.chat.completions.create(
            model=model or settings.DEFAULT_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
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
                # get_user_blog_posts 툴의 경우 user_id를 자동으로 주입
                if tool_name == "get_user_blog_posts":
                    params["user_id"] = request.user_id  # 요청 본문에서 사용자 ID 추출
                
                # 주석 처리: RAG 툴 관련 로직은 다음 학기 구현 예정
                # RAG 툴의 경우 user_id를 자동으로 주입
                # if tool_name in ["search_vector_db", "search_graph_db"]:
                #     params["user_id"] = request.user_id  # 요청 본문에서 사용자 ID 추출
                
                # 모든 툴은 일반 실행
                result = await _execute_regular_tool(
                    tool_name,
                    params,
                    user_api_key=None,
                )
                
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
        successful_tools = [tc.tool for tc in executed_tool_calls if tc.success]
        failed_tools = [tc.tool for tc in executed_tool_calls if not tc.success]
        
        # LLM에게 툴 실행 결과를 전달하여 최종 응답 생성
        if settings.OPENAI_API_KEY:
            try:
                final_response = await _generate_final_response(
                    request.prompt,
                    executed_tool_calls,
                    request.model
                )
            except Exception as e:
                logger.error(f"Failed to generate final response from LLM: {e}")
                # 폴백 응답
                final_response = _create_fallback_response(successful_tools, failed_tools)
        else:
            final_response = _create_fallback_response(successful_tools, failed_tools)
        
        return LLMExecuteResult(
            ok=len(failed_tools) == 0,
            thought=thought,
            tool_calls=executed_tool_calls,
            final_response=final_response,
            model_used=request.model or settings.DEFAULT_LLM_MODEL
        )
        
    except Exception as e:
        logger.error(f"Error executing LLM command: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute LLM command: {str(e)}"
        )


async def _generate_final_response(
    original_prompt: str,
    tool_calls: list[ToolCall],
    model: str = None
) -> str:
    """Generate final user-friendly response using LLM.
    
    툴 실행 결과를 LLM에게 전달하여 사용자 친화적인 최종 응답을 생성합니다.
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    
    # 툴 실행 결과 요약
    tool_results_summary = []
    for tc in tool_calls:
        status = "✅ 성공" if tc.success else "❌ 실패"
        tool_results_summary.append(
            f"{status} {tc.tool}: {json.dumps(tc.result, ensure_ascii=False)[:200]}"
        )
    
    summary_text = "\n".join(tool_results_summary)
    
    response = await client.chat.completions.create(
        model=model or settings.DEFAULT_LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": "당신은 작업 결과를 사용자에게 친절하고 명확하게 전달하는 어시스턴트입니다."
            },
            {
                "role": "user",
                "content": f"""사용자 요청: {original_prompt}

실행된 작업 결과:
{summary_text}

위 결과를 바탕으로 사용자에게 친절하고 명확한 최종 응답을 한국어로 작성해주세요.
간결하게 2-3문장으로 요약해주세요."""
            }
        ],
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

