"""Tests for LLM agent execution endpoint."""
import pytest


def test_execute_llm_command_with_blog_request(client, api_headers):
    """Test LLM command execution for blog posting."""
    request_data = {
        "prompt": "블로그에 이 내용 올려줘",
        "context": {
            "content": "테스트 내용입니다."
        }
    }
    
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "tool_calls" in data
    assert len(data["tool_calls"]) > 0
    assert "final_response" in data
    
    # Check if blog tool was called
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "post_blog_article" in tool_names


def test_execute_llm_command_with_index_request(client, api_headers):
    """Test LLM command execution for index update."""
    request_data = {
        "prompt": "코드 변경사항을 인덱스에 반영해줘",
        "context": {
            "diff": {
                "files": [
                    {
                        "path": "src/test.py",
                        "status": "modified",
                        "content": "def test(): pass"
                    }
                ]
            }
        }
    }
    
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "tool_calls" in data
    
    # Check if index update tool was called
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "update_code_index" in tool_names


def test_execute_llm_command_with_multiple_tasks(client, api_headers):
    """Test LLM command execution with multiple tasks."""
    request_data = {
        "prompt": "코드를 인덱스에 추가하고 블로그 글도 써줘",
        "context": {
            "diff": {
                "files": [
                    {
                        "path": "src/main.py",
                        "status": "modified"
                    }
                ]
            }
        }
    }
    
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert len(data["tool_calls"]) >= 2  # Should call multiple tools
    
    tool_names = [tc["tool"] for tc in data["tool_calls"]]
    assert "update_code_index" in tool_names
    assert "post_blog_article" in tool_names


def test_execute_llm_command_with_custom_model(client, api_headers):
    """Test LLM command execution with custom model."""
    request_data = {
        "prompt": "테스트 작업을 수행해줘",
        "model": "claude-3-5-sonnet"
    }
    
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "model_used" in data


def test_execute_llm_command_without_api_key(client):
    """Test that LLM execution requires API key."""
    response = client.post(
        "/api/v1/llm/execute",
        json={"prompt": "테스트"}
    )
    
    assert response.status_code == 401


def test_execute_llm_command_with_thought_process(client, api_headers):
    """Test that LLM execution returns thought process."""
    request_data = {
        "prompt": "이 작업을 수행해줘",
        "context": {}
    }
    
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "thought" in data
    assert "final_response" in data


def test_execute_llm_command_with_max_iterations(client, api_headers):
    """Test LLM command execution with max iterations limit."""
    request_data = {
        "prompt": "복잡한 작업을 수행해줘",
        "max_iterations": 3
    }
    
    response = client.post(
        "/api/v1/llm/execute",
        json=request_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should not exceed max_iterations
    assert len(data["tool_calls"]) <= 3

