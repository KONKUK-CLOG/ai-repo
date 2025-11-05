"""LLM agent endpoints for natural language command execution."""
from fastapi import APIRouter, Depends, HTTPException, status
from src.server.deps import get_current_user
from src.models.user import User
from src.server.schemas import (
    LLMExecuteRequest,
    LLMExecuteResult,
    ToolCall
)
from src.server.settings import settings
from openai import AsyncOpenAI
from src.mcp.tools import (
    post_blog_article,
    update_code_index,
    publish_to_notion,
    create_commit_and_push
)
import logging
import json

router = APIRouter(prefix="/api/v1/llm", tags=["llm-agent"])
logger = logging.getLogger(__name__)

# ============================================================================
# 툴 레지스트리 (Tool Registry)
# ============================================================================

# 사용 가능한 모든 툴의 중앙 레지스트리
# agent.py와 commands.py에서 공유하여 사용
TOOLS_REGISTRY = {
    "post_blog_article": post_blog_article,           # 블로그 글 발행
    "update_code_index": update_code_index,           # 코드 인덱스 업데이트
    "publish_to_notion": publish_to_notion,           # Notion 페이지 발행
    "create_commit_and_push": create_commit_and_push, # Git 커밋 & 푸시
}


async def _execute_regular_tool(tool_name: str, params: dict) -> dict:
    """Execute a regular tool by name with given parameters.
    
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


def _calculate_dynamic_top_k(max_tokens: int) -> int:
    """Calculate optimal top_k based on LLM max_tokens setting.
    
    Args:
        max_tokens: Maximum tokens for LLM
        
    Returns:
        Optimal number of documents to retrieve
    """
    # Rough estimation: 
    # - Each code file ~500 tokens on average
    # - Reserve 50% of context for prompt + response
    available_tokens = max_tokens * 0.5
    top_k = int(available_tokens / 500)
    
    # Clamp between 3 and 30
    return max(3, min(30, top_k))


async def _execute_blog_article_with_rag(
    prompt: str,
    params: dict,
    user: User,
    model: str = None
) -> dict:
    """Execute blog article posting with RAG-enhanced content generation.
    
    이 함수는 2단계 추론을 수행합니다:
    1. RAG로 관련 코드베이스 검색
    2. LLM이 검색 결과를 바탕으로 블로그 글 생성
    
    Args:
        prompt: User's original prompt
        params: Tool parameters (may contain partial info)
        user: Authenticated user
        model: LLM model to use
        
    Returns:
        Blog article publication result
    """
    from src.adapters import vector_db
    
    logger.info(f"Executing blog article with RAG for prompt: {prompt}")
    
    # 1. Calculate optimal top_k and split between DBs
    max_tokens = settings.LLM_MAX_TOKENS
    total_top_k = _calculate_dynamic_top_k(max_tokens)
    
    # Split top_k: 70% for Vector DB (code content), 30% for Graph DB (structure)
    vector_top_k = max(3, int(total_top_k * 0.7))  # At least 3
    graph_top_k = max(2, int(total_top_k * 0.3))   # At least 2
    
    logger.info(f"Allocating top_k - Total: {total_top_k}, Vector: {vector_top_k}, Graph: {graph_top_k}")
    
    # 2. Perform RAG search using user's prompt
    # 2-1. Vector DB: Semantic search (priority - full code content)
    vector_results = await vector_db.semantic_search(
        collection=settings.VECTOR_DB_COLLECTION,
        query=prompt,
        user_id=user.id,
        top_k=vector_top_k
    )
    logger.info(f"Vector DB search returned {len(vector_results)} documents")
    
    # 2-2. Track files from Vector DB to avoid duplicates
    vector_files = {result['file'] for result in vector_results}
    
    # 2-3. Graph DB: Related code entities search
    from src.adapters import graph_db
    graph_results_raw = await graph_db.search_related_code(
        query=prompt,
        user_id=user.id,
        limit=graph_top_k * 3  # Get more to compensate for filtering
    )
    
    # 2-4. Filter out files already in Vector DB results (deduplication)
    graph_results = [
        r for r in graph_results_raw 
        if r['file'] not in vector_files
    ][:graph_top_k]  # Limit to graph_top_k
    
    logger.info(f"Graph DB search returned {len(graph_results_raw)} entities, "
                f"{len(graph_results)} unique after deduplication")
    
    # 3. Format RAG results for LLM context
    rag_context = []
    
    # 3-1. Vector DB results: Full code content (핵심 코드)
    if vector_results:
        rag_context.append("## 📄 핵심 코드 (의미적 유사도)\n")
        for idx, result in enumerate(vector_results, 1):
            rag_context.append(
                f"**{idx}. {result['file']}** (유사도: {result['score']:.3f})\n"
                f"```\n{result['content']}\n```\n"
            )
    
    # 3-2. Graph DB results: Concise entity descriptions (추가 관련 엔티티)
    if graph_results:
        rag_context.append("\n## 🔗 추가 관련 코드 엔티티\n")
        for result in graph_results:
            calls_info = ""
            if result.get("calls"):
                calls_list = ', '.join(result['calls'][:3])
                calls_info = f" (calls: {calls_list})"
            
            # Single-line format for efficiency
            rag_context.append(
                f"- **{result['file']}**: `{result['entity_name']}` "
                f"({result['entity_type']}){calls_info}\n"
            )
    
    rag_context_str = "\n".join(rag_context) if rag_context else "관련 코드를 찾을 수 없습니다."
    
    # 4. Call LLM to generate blog content
    if not settings.OPENAI_API_KEY:
        # Fallback: use simple content generation
        return await post_blog_article.run({
            "title": params.get("title", "자동 생성된 글"),
            "markdown": params.get("markdown", f"# 코드 변경 요약\n\n{prompt}"),
            "tags": params.get("tags", [])
        })
    
    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        
        system_prompt = """당신은 기술 블로그 작성자입니다. 
제공된 코드베이스 정보를 바탕으로 정확하고 유익한 기술 블로그 글을 작성하세요.

요구사항:
- 제목과 본문을 markdown 형식으로 작성
- 코드 예제를 적절히 활용
- 기술적 정확성 유지
- 독자가 이해하기 쉽게 설명
- JSON 형식으로 응답: {"title": "...", "markdown": "..."}"""

        user_message = f"""사용자 요청: {prompt}

관련 코드베이스:
{rag_context_str}

위 정보를 바탕으로 블로그 글을 작성해주세요. 
제목과 마크다운 본문을 JSON 형식으로 반환해주세요."""

        response = await client.chat.completions.create(
            model=model or settings.DEFAULT_LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            temperature=0.7,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        blog_data = json.loads(content)
        
        # 5. Publish blog article with generated content
        result = await post_blog_article.run({
            "title": blog_data.get("title", params.get("title", "자동 생성된 글")),
            "markdown": blog_data.get("markdown", params.get("markdown", "")),
            "tags": params.get("tags", [])
        })
        
        logger.info(f"Successfully published blog article with RAG")
        return result
        
    except Exception as e:
        logger.error(f"Failed to generate blog content with LLM: {e}")
        # Fallback to simple generation
        return await post_blog_article.run({
            "title": params.get("title", "자동 생성된 글"),
            "markdown": params.get("markdown", f"# {prompt}\n\n관련 코드:\n{rag_context_str}"),
            "tags": params.get("tags", [])
        })


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
    system_prompt = """당신은 코드 관리 및 문서화 작업을 돕는 AI 어시스턴트입니다.
사용자의 요청을 분석하여 적절한 툴을 선택하고 실행하세요.

사용 가능한 툴:
- post_blog_article: 블로그에 글 발행
- update_code_index: 코드 변경사항을 벡터/그래프 인덱스에 반영
- publish_to_notion: Notion에 페이지 발행
- create_commit_and_push: Git 커밋 후 푸시

컨텍스트에 있는 정보를 최대한 활용하여 적절한 파라미터를 구성하세요."""
    
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
    
    # 아무 툴도 선택되지 않은 경우
    if not tool_calls:
        thought = "요청을 처리할 적절한 툴을 찾지 못했습니다. 구체적인 작업을 명시해주세요."
    
    return thought, tool_calls


@router.post("/execute", response_model=LLMExecuteResult)
async def execute_llm_command(
    request: LLMExecuteRequest,
    user: User = Depends(get_current_user)
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
                # 블로그 글 작성은 RAG를 사용한 2단계 추론
                if tool_name == "post_blog_article":
                    logger.info("Using RAG-enhanced execution for blog article")
                    result = await _execute_blog_article_with_rag(
                        prompt=request.prompt,
                        params=params,
                        user=user,
                        model=request.model
                    )
                else:
                    # 다른 툴들은 일반 실행
                    result = await _execute_regular_tool(tool_name, params)
                
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

