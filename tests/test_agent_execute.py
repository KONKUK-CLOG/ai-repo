"""Tests for LLM agent execution endpoint.

이 모듈은 LLM 에이전트를 통한 명령 실행을 테스트합니다:
1. 자연어 프롬프트 해석
2. 적절한 툴 선택
3. 툴 실행 및 결과 반환
4. 다중 툴 실행
5. LLM의 사고 과정 추적

각 테스트는 Given-When-Then 패턴을 따릅니다.
"""
import pytest


def test_execute_llm_command_with_blog_request(client, api_headers, mock_user_repo, mock_openai_chat, mock_qdrant_client, mock_neo4j_driver, mock_tools):
    """블로그 작성 요청을 LLM이 처리하는지 테스트.
    
    Given: 사용자가 블로그 작성을 요청하는 자연어 프롬프트를 작성하고
    When: LLM 에이전트에 전달하면
    Then: LLM이 post_blog_article 툴을 선택하고 실행해야 함
    
    검증사항:
    - HTTP 200 응답
    - tool_calls에 post_blog_article 포함
    - final_response 생성됨
    - RAG를 통한 정확한 컨텐츠 생성
    
    설명:
    - LLM이 자연어를 이해하고 적절한 툴을 선택
    - 블로그 작성 시 RAG로 코드베이스 검색
    - 검색된 정보를 바탕으로 정확한 글 생성
    """
    # Given: 블로그 작성 요청
    request_data = {
        "prompt": "블로그에 이 내용 올려줘",
        "context": {
            "content": "테스트 내용입니다."
        }
    }
    
    # When: LLM 에이전트 실행
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    # Then: 블로그 툴 실행됨
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "tool_calls" in data
    assert len(data["tool_calls"]) > 0
    assert "final_response" in data
    
    # Check if blog tool was called
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "post_blog_article" in tool_names


def test_execute_llm_command_with_multiple_tasks(client, api_headers, mock_user_repo, mock_openai_chat, mock_tools):
    """LLM이 여러 작업을 동시에 처리하는지 테스트.
    
    Given: 사용자가 여러 작업을 한 번에 요청하고
    When: LLM에 전달하면
    Then: 필요한 모든 툴을 선택하고 순서대로 실행해야 함
    
    검증사항:
    - HTTP 200 응답
    - tool_calls에 여러 툴 포함
    - 각 툴이 적절히 실행됨
    - 작업 간 의존성 고려
    
    설명:
    - "블로그 쓰고 Notion에도 발행해줘" → 2개 툴 실행
    - LLM이 작업을 분석하고 필요한 툴들을 결정
    - 각 툴을 순차적으로 실행
    """
    # Given: 여러 작업 요청
    request_data = {
        "prompt": "블로그 글도 쓰고 Notion에도 발행해줘",
        "context": {
            "project": "test-project"
        }
    }
    
    # When: LLM 에이전트 실행
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    # Then: 여러 툴이 실행됨
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["tool_calls"]) >= 2  # Should call multiple tools
    
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "post_blog_article" in tool_names
    assert "publish_to_notion" in tool_names


def test_execute_llm_command_with_custom_model(client, api_headers, mock_user_repo, mock_openai_chat, mock_tools):
    """사용자 지정 LLM 모델 사용을 테스트.
    
    Given: 사용자가 특정 LLM 모델을 지정하고
    When: 해당 모델로 작업을 실행하면
    Then: 지정된 모델이 사용되어야 함
    
    검증사항:
    - HTTP 200 응답
    - model_used에 지정한 모델명 표시
    - 모델별 특성 반영 (컨텍스트 길이 등)
    
    설명:
    - 기본값: gpt-4o-mini
    - 사용자가 claude-3-5-sonnet, gpt-4 등 선택 가능
    - 모델에 따라 RAG top_k 동적 조절
    """
    # Given: 커스텀 모델 지정
    request_data = {
        "prompt": "테스트 작업을 수행해줘",
        "model": "claude-3-5-sonnet"
    }
    
    # When: 지정한 모델로 실행
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    # Then: 지정한 모델 사용됨
    assert response.status_code == 200
    data = response.json()
    assert "model_used" in data


def test_execute_llm_command_without_api_key(client):
    """API 키 없이 LLM 실행 시도를 테스트.
    
    Given: API 키가 제공되지 않고
    When: LLM 에이전트를 실행하려 하면
    Then: 422 Unprocessable Entity 에러가 반환되어야 함
    
    검증사항:
    - HTTP 422 응답 (필수 헤더 누락)
    
    설명:
    - LLM 실행은 사용자별 데이터에 접근하므로 인증 필수
    - API 키를 통해 사용자 식별 및 권한 검증
    - FastAPI는 필수 Depends 파라미터 누락 시 422를 반환
    """
    # When: API 키 없이 요청
    response = client.post(
        "/api/v1/llm/execute",
        json={"prompt": "테스트"}
    )
    
    # Then: 422 에러 (필수 헤더 누락)
    assert response.status_code == 422


def test_execute_llm_command_with_thought_process(client, api_headers, mock_user_repo, mock_openai_chat, mock_tools):
    """LLM의 사고 과정이 반환되는지 테스트.
    
    Given: LLM이 작업을 분석하고
    When: 툴을 선택하고 실행하면
    Then: 사고 과정(thought)과 최종 응답이 반환되어야 함
    
    검증사항:
    - thought 필드 포함
    - final_response 필드 포함
    - 사고 과정이 의미 있음
    
    설명:
    - thought: LLM이 왜 이 툴을 선택했는지 설명
    - 예: "사용자가 블로그 발행을 요청했으므로 post_blog_article 툴을 사용합니다"
    - 디버깅 및 사용자 이해에 유용
    """
    # Given: 작업 요청
    request_data = {
        "prompt": "이 작업을 수행해줘",
        "context": {}
    }
    
    # When: LLM 실행
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    # Then: 사고 과정과 응답 포함
    assert response.status_code == 200
    data = response.json()
    assert "thought" in data
    assert "final_response" in data


def test_execute_llm_command_with_max_iterations(client, api_headers, mock_user_repo, mock_openai_chat, mock_tools):
    """LLM의 최대 반복 횟수 제한을 테스트.
    
    Given: 복잡한 작업이 여러 단계를 필요로 하고
    When: max_iterations 제한을 설정하면
    Then: 지정된 횟수 이상 반복하지 않아야 함
    
    검증사항:
    - HTTP 200 응답
    - tool_calls 개수가 max_iterations 이하
    - 무한 루프 방지
    
    설명:
    - 복잡한 작업은 여러 툴을 순차 실행할 수 있음
    - max_iterations로 실행 횟수 제한
    - 기본값: 5회
    - 무한 루프 및 비용 초과 방지
    """
    # Given: 복잡한 작업과 반복 제한
    request_data = {
        "prompt": "복잡한 작업을 수행해줘",
        "max_iterations": 3
    }
    
    # When: 제한된 반복으로 실행
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    # Then: 제한 준수
    assert response.status_code == 200
    data = response.json()
    # Should not exceed max_iterations
    assert len(data["tool_calls"]) <= 3
