"""Tests for command execution endpoint."""
import pytest


def test_list_commands(client, api_headers):
    """Test listing available commands."""
    response = client.get(
        "/api/v1/commands",
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) > 0
    
    # Check that post_blog_article is in the list
    tool_names = [tool["name"] for tool in data["tools"]]
    assert "post_blog_article" in tool_names


def test_execute_post_blog_article(client, api_headers):
    """Test executing post_blog_article command."""
    command_data = {
        "name": "post_blog_article",
        "params": {
            "title": "Test Article",
            "markdown": "# Hello World\n\nThis is a test."
        }
    }
    
    response = client.post(
        "/api/v1/commands/execute",
        json=command_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["tool"] == "post_blog_article"
    assert "result" in data


def test_execute_update_code_index(client, api_headers):
    """Test executing update_code_index command."""
    command_data = {
        "name": "update_code_index",
        "params": {
            "files": [
                {
                    "path": "src/test.py",
                    "content": "def test(): pass",
                    "status": "modified"
                }
            ]
        }
    }
    
    response = client.post(
        "/api/v1/commands/execute",
        json=command_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["tool"] == "update_code_index"


def test_execute_with_idempotency_key(client, api_headers):
    """Test command execution with idempotency key."""
    headers = {
        **api_headers,
        "x-idempotency-key": "test-key-123"
    }
    
    command_data = {
        "name": "refresh_rag_indexes",
        "params": {"full_rebuild": False}
    }
    
    response = client.post(
        "/api/v1/commands/execute",
        json=command_data,
        headers=headers
    )
    
    assert response.status_code == 200


def test_execute_without_api_key(client):
    """Test that command execution requires API key."""
    response = client.post(
        "/api/v1/commands/execute",
        json={"name": "post_blog_article", "params": {}}
    )
    
    assert response.status_code == 401


def test_execute_nonexistent_tool(client, api_headers):
    """Test executing non-existent tool."""
    command_data = {
        "name": "nonexistent_tool",
        "params": {}
    }
    
    response = client.post(
        "/api/v1/commands/execute",
        json=command_data,
        headers=api_headers
    )
    
    assert response.status_code == 400

