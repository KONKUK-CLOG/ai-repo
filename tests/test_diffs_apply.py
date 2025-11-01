"""Tests for diff application endpoint."""
import pytest


def test_apply_diff_unified_mode(client, api_headers):
    """Test applying diff in unified mode."""
    diff_content = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def hello():
-    print("hello")
+    print("hello world")
"""
    
    response = client.post(
        "/api/v1/diffs/apply",
        json={"unified": diff_content},
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "files_processed" in data
    assert "embeddings_upserted" in data
    assert "graph_nodes_updated" in data
    assert "stats" in data


def test_apply_diff_files_mode(client, api_headers):
    """Test applying diff in files mode."""
    files_data = {
        "files": [
            {
                "path": "src/main.py",
                "status": "modified",
                "before": "print('hello')",
                "after": "print('hello world')"
            },
            {
                "path": "src/new.py",
                "status": "added",
                "after": "def new_func(): pass"
            }
        ]
    }
    
    response = client.post(
        "/api/v1/diffs/apply",
        json=files_data,
        headers=api_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["files_processed"] == 2
    assert "embeddings_upserted" in data
    assert "stats" in data


def test_apply_diff_without_api_key(client):
    """Test that diff application requires API key."""
    response = client.post(
        "/api/v1/diffs/apply",
        json={"files": []}
    )
    
    assert response.status_code == 401


def test_apply_diff_invalid_input(client, api_headers):
    """Test applying diff with invalid input."""
    response = client.post(
        "/api/v1/diffs/apply",
        json={},  # Neither unified nor files provided
        headers=api_headers
    )
    
    assert response.status_code == 400

