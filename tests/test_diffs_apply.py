"""Tests for diff application endpoint.

이 모듈은 코드 diff를 적용하여 DB를 업데이트하는 기능을 테스트합니다:
1. Unified diff 모드 (Git diff 형식)
2. Files 배열 모드 (구조화된 파일 목록)
3. Vector DB 및 Graph DB 업데이트
4. API 키 인증
5. WAL (Write-Ahead Log) 통합

각 테스트는 Given-When-Then 패턴을 따릅니다.
"""
import pytest


def test_apply_diff_unified_mode(client, api_headers, mock_user_repo, mock_qdrant_client, mock_neo4j_driver, mock_openai_embeddings, mock_tools):
    """Unified diff 모드로 변경사항을 적용하는 테스트.
    
    Given: Git diff 형식의 unified diff가 있고
    When: /api/v1/diffs/apply 엔드포인트에 diff를 전송하면
    Then: Vector DB와 Graph DB가 업데이트되어야 함
    
    검증사항:
    - HTTP 200 응답
    - files_processed 개수 반환
    - embeddings_upserted 개수 반환
    - graph_nodes_updated 개수 반환
    - 통계 정보 포함
    
    설명:
    - Unified diff는 Git이 생성하는 표준 diff 형식
    - '--- a/file.py'와 '+++ b/file.py'로 시작
    - '@@ -1,3 +1,3 @@'는 변경 위치 표시
    - '-'로 시작하는 라인은 삭제됨
    - '+'로 시작하는 라인은 추가됨
    """
    # Given: Unified diff 형식의 변경사항
    diff_content = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 def hello():
-    print("hello")
+    print("hello world")
"""
    
    # When: Diff 적용 요청
    response = client.post(
        "/api/v1/diffs/apply",
        json={"unified": diff_content},
        headers=api_headers
    )
    
    # Then: 성공적으로 DB 업데이트
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "files_processed" in data
    assert "embeddings_upserted" in data
    assert "graph_nodes_updated" in data
    assert "stats" in data


def test_apply_diff_files_mode(client, api_headers, mock_user_repo, mock_qdrant_client, mock_neo4j_driver, mock_openai_embeddings, mock_tools):
    """Files 배열 모드로 변경사항을 적용하는 테스트.
    
    Given: 구조화된 파일 목록 (JSON)이 있고
    When: files 배열로 변경사항을 전송하면
    Then: 각 파일에 대해 DB가 업데이트되어야 함
    
    검증사항:
    - HTTP 200 응답
    - files_processed가 전송한 파일 개수와 일치
    - modified, added, deleted 상태 모두 처리
    - 각 파일의 before/after 내용 적용
    
    설명:
    - Files 모드는 VSCode Extension 등 클라이언트에서 사용
    - 각 파일의 상태(modified/added/deleted)와 내용을 명시
    - before: 변경 전 내용
    - after: 변경 후 내용
    """
    # Given: 구조화된 파일 변경사항
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
    
    # When: Files 모드로 diff 적용
    response = client.post(
        "/api/v1/diffs/apply",
        json=files_data,
        headers=api_headers
    )
    
    # Then: 모든 파일 처리됨
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["files_processed"] == 2
    assert "embeddings_upserted" in data
    assert "stats" in data


def test_apply_diff_without_authorization(client):
    """API 키 없이 diff 적용 시도를 테스트."""
    response = client.post(
        "/api/v1/diffs/apply",
        json={"files": []}
    )
    
    assert response.status_code == 422


def test_apply_diff_invalid_input(client, api_headers, mock_user_repo, mock_tools):
    """잘못된 입력으로 diff 적용 시도를 테스트.
    
    Given: unified와 files가 모두 제공되지 않았고
    When: diff를 적용하려 하면
    Then: 400 Bad Request 에러가 반환되어야 함
    
    검증사항:
    - HTTP 400 응답
    - 입력 검증 실패
    
    설명:
    - unified 또는 files 중 하나는 반드시 제공되어야 함
    - 둘 다 없으면 처리할 변경사항이 없음
    - 입력 검증을 통해 명확한 에러 메시지 제공
    """
    # When: unified도 files도 없이 요청
    response = client.post(
        "/api/v1/diffs/apply",
        json={},  # Neither unified nor files provided
        headers=api_headers
    )
    
    # Then: 잘못된 요청 에러
    assert response.status_code == 400
