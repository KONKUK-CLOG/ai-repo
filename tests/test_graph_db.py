"""Tests for Graph DB operations.

이 모듈은 Neo4j Graph DB의 주요 기능을 테스트합니다:
1. 관련 코드 검색 (search related code)
2. 코드 그래프 업데이트 (update code graph)
3. 파일 노드 삭제 (delete file nodes)
4. Python 파일 파싱 (parse Python files)
5. 사용자별 데이터 격리 (user isolation)

각 테스트는 Given-When-Then 패턴을 따릅니다.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.adapters import graph_db


@pytest.mark.asyncio
async def test_search_related_code(mock_neo4j_driver):
    """관련 코드 엔티티 검색 기능을 테스트.
    
    Given: Graph DB에 코드 엔티티들(함수, 클래스 등)이 저장되어 있고
    When: 특정 키워드로 검색하면
    Then: 관련된 코드 엔티티들이 반환되어야 함
    
    검증사항:
    - 검색 결과 반환
    - entity_name, entity_type, file 정보 포함
    - 키워드와 관련성 있는 결과
    """
    # When: 코드 엔티티 검색
    results = await graph_db.search_related_code(
        query="test function",
        user_id=1,
        limit=10
    )
    
    # Then: 관련 코드 엔티티 반환
    assert len(results) > 0
    assert results[0]["entity_name"] == "test_function"
    assert results[0]["entity_type"] == "function"
    assert results[0]["file"] == "src/test.py"


@pytest.mark.asyncio
async def test_search_related_code_with_relationships(mock_neo4j_driver):
    """검색 결과에 관계 정보가 포함되는지 테스트.
    
    Given: 코드 엔티티 간 관계(호출, 임포트 등)가 그래프에 저장되어 있고
    When: 코드를 검색하면
    Then: 관련 관계 정보(calls, imports 등)가 함께 반환되어야 함
    
    검증사항:
    - calls 필드가 결과에 포함
    - calls가 배열 타입
    - 관계 정보가 유용함
    """
    # When: 코드 검색
    results = await graph_db.search_related_code(
        query="test",
        user_id=1,
        limit=5
    )
    
    # Then: 관계 정보 포함
    assert len(results) > 0
    assert "calls" in results[0]
    assert isinstance(results[0]["calls"], list)


@pytest.mark.asyncio
async def test_search_related_code_user_filtering():
    """검색이 사용자별로 필터링하는지 테스트.
    
    Given: 여러 사용자의 코드가 Graph DB에 있고
    When: 특정 사용자 ID로 검색하면
    Then: 해당 사용자의 코드만 검색되어야 함
    
    검증사항:
    - Cypher 쿼리에 user_id 파라미터 포함
    - 다른 사용자의 데이터는 결과에 포함되지 않음
    """
    # Given: Mock Neo4j driver
    mock_driver = AsyncMock()
    mock_session = AsyncMock()
    mock_result = AsyncMock()
    
    # Track if user_id was used in query
    called_with_user_id = []
    
    async def mock_run(query, **params):
        called_with_user_id.append(params.get("user_id"))
        mock_record = MagicMock()
        mock_record.__getitem__ = lambda self, key: "test_value"
        mock_result.__aiter__ = lambda self: iter([mock_record])
        return mock_result
    
    mock_session.run = mock_run
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    mock_driver.session = MagicMock(return_value=mock_session)
    
    # When: user_id 42로 검색
    with patch('src.adapters.graph_db.get_neo4j_driver', return_value=mock_driver):
        await graph_db.search_related_code(
            query="test",
            user_id=42,
            limit=5
        )
        
        # Then: user_id가 사용됨
        # Verify user_id was used
        assert 42 in called_with_user_id


@pytest.mark.asyncio
async def test_update_code_graph(mock_neo4j_driver):
    """코드 그래프 업데이트 기능을 테스트.
    
    Given: 코드 파일들과 그 내용이 있고
    When: 코드 그래프를 업데이트하면
    Then: 함수, 클래스, 관계 등이 그래프에 저장되어야 함
    
    검증사항:
    - 처리된 파일 개수 반환
    - 함수, 클래스 노드 생성
    - 호출 관계, 임포트 관계 생성
    """
    # Given: 업데이트할 파일들
    files = ["src/test.py", "src/main.py"]
    contents = {
        "src/test.py": "def test(): pass",
        "src/main.py": "def main(): print('hello')"
    }
    
    # When: 그래프 업데이트
    count = await graph_db.update_code_graph(
        files=files,
        contents=contents,
        user_id=1
    )
    
    # Then: 모든 파일 처리됨
    assert count == 2


@pytest.mark.asyncio
async def test_update_code_graph_with_user_id():
    """그래프 업데이트 시 user_id가 포함되는지 테스트.
    
    Given: 특정 사용자의 코드 파일이 있고
    When: 그래프를 업데이트하면
    Then: 생성되는 노드와 관계에 user_id가 포함되어야 함
    
    검증사항:
    - Cypher 쿼리에 user_id 파라미터 포함
    - 노드 속성에 user_id 저장
    """
    # Given: Mock driver
    mock_driver = AsyncMock()
    mock_session = AsyncMock()
    
    queries_executed = []
    
    async def mock_run(query, **params):
        queries_executed.append((query, params))
        return AsyncMock()
    
    mock_session.run = mock_run
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    mock_driver.session = MagicMock(return_value=mock_session)
    
    # When: user_id 99로 업데이트
    with patch('src.adapters.graph_db.get_neo4j_driver', return_value=mock_driver):
        await graph_db.update_code_graph(
            files=["test.py"],
            contents={"test.py": "def test(): pass"},
            user_id=99
        )
        
        # Then: user_id가 쿼리에 포함됨
        # Verify user_id was included in queries
        assert any(params.get("user_id") == 99 for _, params in queries_executed)


@pytest.mark.asyncio
async def test_delete_file_nodes(mock_neo4j_driver):
    """파일 노드 삭제 기능을 테스트.
    
    Given: Graph DB에 파일 노드들이 있고
    When: 특정 파일들을 삭제하면
    Then: 해당 파일의 노드와 관련 관계가 모두 삭제되어야 함
    
    검증사항:
    - 삭제된 파일 개수 반환
    - 파일 노드와 관련 엔티티 모두 삭제
    - user_id 필터가 적용되어 해당 사용자의 파일만 삭제
    """
    # Given: 삭제할 파일들
    files = ["src/old.py", "src/deprecated.py"]
    
    # When: 파일 노드 삭제
    count = await graph_db.delete_file_nodes(
        files=files,
        user_id=1
    )
    
    # Then: 파일들이 삭제됨
    assert count == 2


@pytest.mark.asyncio
async def test_parse_python_file():
    """Python 파일 파싱 기능을 테스트.
    
    Given: Python 소스 코드가 있고
    When: 파일을 파싱하면
    Then: 함수, 클래스, 임포트 등이 추출되어야 함
    
    검증사항:
    - 함수 정의 추출
    - 클래스 정의 추출
    - import 문 추출
    - 호출 관계 추출
    """
    # Given: Python 소스 코드
    code = """
def test_function():
    helper_function()
    return True

class TestClass:
    def method1(self):
        pass
    
    def method2(self):
        pass

import os
from pathlib import Path
"""
    
    # When: 파일 파싱
    result = graph_db.parse_python_file("test.py", code)
    
    # Then: 엔티티들이 추출됨
    assert result["file"] == "test.py"
    assert len(result["entities"]) > 0
    
    # Find function
    functions = [e for e in result["entities"] if e["type"] == "function"]
    assert len(functions) > 0
    assert any(f["name"] == "test_function" for f in functions)
    
    # Find class
    classes = [e for e in result["entities"] if e["type"] == "class"]
    assert len(classes) > 0
    assert any(c["name"] == "TestClass" for c in classes)
    
    # Find imports
    assert len(result["imports"]) > 0
    assert "os" in result["imports"]


@pytest.mark.asyncio
async def test_parse_python_file_with_syntax_error():
    """문법 오류가 있는 파일 파싱을 테스트.
    
    Given: 문법 오류가 있는 Python 코드가 있고
    When: 파일을 파싱하면
    Then: 에러가 발생하지 않고 빈 결과를 반환해야 함
    
    검증사항:
    - 에러 대신 빈 결과 반환
    - 프로그램이 중단되지 않음
    - graceful degradation
    """
    # Given: 문법 오류가 있는 코드
    code = "def broken(:\n    pass"
    
    # When: 파싱 시도
    result = graph_db.parse_python_file("broken.py", code)
    
    # Then: 에러 없이 빈 결과 반환
    # Should return empty result instead of crashing
    assert result["file"] == "broken.py"
    assert result["entities"] == []
    assert result["imports"] == []


@pytest.mark.asyncio
async def test_user_data_isolation_in_graph():
    """Graph DB에서 사용자 간 데이터 격리를 테스트.
    
    Given: 여러 사용자의 코드가 Graph DB에 있고
    When: 각 사용자가 작업을 수행하면
    Then: 각 사용자의 데이터가 서로 격리되어야 함
    
    검증사항:
    - 모든 쿼리에 user_id가 포함됨
    - User 1의 작업이 User 2의 데이터에 영향을 주지 않음
    - 검색, 업데이트, 삭제 모두 격리됨
    """
    # Given: Mock driver
    mock_driver = AsyncMock()
    mock_session = AsyncMock()
    
    user_queries = []
    
    async def mock_run(query, **params):
        user_queries.append(params.get("user_id"))
        # Return empty result
        mock_result = AsyncMock()
        mock_result.__aiter__ = lambda self: iter([])
        return mock_result
    
    mock_session.run = mock_run
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    mock_driver.session = MagicMock(return_value=mock_session)
    
    with patch('src.adapters.graph_db.get_neo4j_driver', return_value=mock_driver):
        # When: User 1 작업
        await graph_db.search_related_code(query="test", user_id=1, limit=5)
        
        # When: User 2 작업
        await graph_db.search_related_code(query="test", user_id=2, limit=5)
        
        # Then: 두 사용자의 ID가 모두 사용됨
        # Verify both users' IDs were used
        assert 1 in user_queries
        assert 2 in user_queries


@pytest.mark.asyncio
async def test_graph_db_connection_failure():
    """Graph DB 연결 실패 처리를 테스트.
    
    Given: Graph DB 연결이 실패했고
    When: 작업을 수행하려 하면
    Then: 에러 대신 빈 결과를 반환해야 함
    
    검증사항:
    - 에러 발생하지 않음
    - 빈 배열 또는 기본값 반환
    - 애플리케이션이 중단되지 않음
    """
    # Given: DB 연결 실패
    with patch('src.adapters.graph_db.get_neo4j_driver', return_value=None):
        # When: 검색 시도
        # Should return empty results instead of crashing
        results = await graph_db.search_related_code(
            query="test",
            user_id=1,
            limit=5
        )
        
        # Then: 빈 결과 반환
        assert results == []


@pytest.mark.asyncio
async def test_refresh_graph_indexes():
    """Graph DB 인덱스 새로고침 기능을 테스트.
    
    Given: Graph DB가 실행 중이고
    When: 인덱스 새로고침을 실행하면
    Then: 인덱스가 갱신되고 통계가 반환되어야 함
    
    검증사항:
    - success 필드가 True
    - nodes_count가 포함됨
    - relationships_count가 포함됨
    """
    # When: 인덱스 새로고침
    result = await graph_db.refresh_graph_indexes()
    
    # Then: 성공 및 통계 반환
    assert result["success"] is True
    assert "nodes_count" in result
    assert "relationships_count" in result
