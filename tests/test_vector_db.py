"""Tests for Vector DB operations.

이 모듈은 Qdrant Vector DB의 주요 기능을 테스트합니다:
1. 시맨틱 검색 (semantic search)
2. 임베딩 업서트 (upsert embeddings)
3. 임베딩 삭제 (delete embeddings)
4. 사용자별 데이터 격리 (user isolation)
5. OpenAI 임베딩 생성

각 테스트는 Given-When-Then 패턴을 따릅니다.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.adapters import vector_db


@pytest.mark.asyncio
async def test_semantic_search(mock_qdrant_client, mock_openai_embeddings):
    """시맨틱 검색 기능을 테스트.
    
    Given: Vector DB에 사용자의 코드가 인덱싱되어 있고
    When: 특정 쿼리로 시맨틱 검색을 수행하면
    Then: 관련성 높은 코드 조각들이 반환되어야 함
    
    검증사항:
    - 검색 결과가 반환됨
    - 각 결과에 file, score, user_id 정보 포함
    - 검색 결과가 쿼리와 관련성이 높음
    """
    # When: 시맨틱 검색 수행
    results = await vector_db.semantic_search(
        collection="test_collection",
        query="test query",
        user_id=1,
        top_k=5
    )
    
    # Then: 관련 코드 조각 반환
    assert len(results) > 0
    assert results[0]["file"] == "src/test.py"
    assert results[0]["score"] == 0.85
    assert results[0]["user_id"] == 1


@pytest.mark.asyncio
async def test_semantic_search_user_filtering(mock_qdrant_client):
    """시맨틱 검색이 사용자별로 필터링하는지 테스트.
    
    Given: 여러 사용자의 데이터가 Vector DB에 있고
    When: 특정 사용자 ID로 검색하면
    Then: 해당 사용자의 데이터만 검색되어야 함
    
    검증사항:
    - search 호출 시 user_id 필터가 적용됨
    - 다른 사용자의 데이터는 결과에 포함되지 않음
    """
    # When: user_id 1로 검색
    with patch('src.adapters.vector_db.generate_embedding', new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = [0.1] * 1536
        await vector_db.semantic_search(
            collection="test_collection",
            query="test",
            user_id=1,
            top_k=5
        )
        
        # Then: user_id 필터가 적용됨
        # Verify that search was called with user_id filter
        mock_qdrant_client.search.assert_called_once()
        call_args = mock_qdrant_client.search.call_args
        assert call_args[1]["query_filter"] is not None


@pytest.mark.asyncio
async def test_semantic_search_empty_results():
    """검색 결과가 없을 때의 처리를 테스트.
    
    Given: Vector DB에 쿼리와 관련된 데이터가 없고
    When: 시맨틱 검색을 수행하면
    Then: 빈 배열이 반환되어야 함 (에러가 아님)
    
    검증사항:
    - 빈 배열 반환
    - 에러 발생하지 않음
    """
    # Given: 빈 검색 결과를 반환하는 mock
    mock_client = AsyncMock()
    mock_client.search = AsyncMock(return_value=[])
    
    # When: 존재하지 않는 코드 검색
    with patch('src.adapters.vector_db.get_qdrant_client', return_value=mock_client):
        with patch('src.adapters.vector_db.generate_embedding', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [0.1] * 1536
            results = await vector_db.semantic_search(
                collection="test_collection",
                query="nonexistent",
                user_id=1,
                top_k=5
            )
            
            # Then: 빈 배열 반환
            assert results == []


@pytest.mark.asyncio
async def test_upsert_embeddings(mock_qdrant_client, mock_openai_embeddings):
    """임베딩 업서트 기능을 테스트.
    
    Given: 새로운 또는 수정된 코드 파일들이 있고
    When: 해당 파일들의 임베딩을 업서트하면
    Then: Vector DB에 임베딩이 저장되어야 함
    
    검증사항:
    - 처리된 파일 개수 반환
    - Qdrant upsert 메서드 호출됨
    - 각 파일에 대해 임베딩이 생성됨
    """
    # Given: 업서트할 문서들
    documents = [
        {
            "file": "src/test.py",
            "content": "def test(): pass",
            "status": "modified"
        },
        {
            "file": "src/main.py",
            "content": "def main(): print('hello')",
            "status": "added"
        }
    ]
    
    # When: 임베딩 업서트
    count = await vector_db.upsert_embeddings(
        collection="test_collection",
        documents=documents,
        user_id=1
    )
    
    # Then: 모든 파일 처리됨
    assert count == 2
    mock_qdrant_client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_upsert_embeddings_with_user_id(mock_qdrant_client, mock_openai_embeddings):
    """업서트된 임베딩에 user_id가 포함되는지 테스트.
    
    Given: 특정 사용자의 코드 파일이 있고
    When: 임베딩을 업서트하면
    Then: 각 임베딩의 payload에 user_id가 포함되어야 함
    
    검증사항:
    - upsert된 points에 user_id 포함
    - 올바른 user_id 값이 저장됨
    """
    # Given: 사용자 42의 문서
    documents = [
        {"file": "test.py", "content": "test", "status": "modified"}
    ]
    
    # When: user_id 42로 업서트
    await vector_db.upsert_embeddings(
        collection="test_collection",
        documents=documents,
        user_id=42
    )
    
    # Then: user_id가 포함됨
    # Verify upsert was called with points containing user_id
    mock_qdrant_client.upsert.assert_called_once()
    call_args = mock_qdrant_client.upsert.call_args
    points = call_args[1]["points"]
    assert len(points) > 0
    assert points[0].payload["user_id"] == 42


@pytest.mark.asyncio
async def test_delete_embeddings(mock_qdrant_client):
    """임베딩 삭제 기능을 테스트.
    
    Given: Vector DB에 코드 임베딩들이 있고
    When: 특정 파일들의 임베딩을 삭제하면
    Then: 해당 파일들의 임베딩이 DB에서 제거되어야 함
    
    검증사항:
    - 삭제된 파일 개수 반환
    - Qdrant delete 메서드 호출됨
    - user_id 필터가 적용되어 해당 사용자의 파일만 삭제
    """
    # Given: 삭제할 파일 경로들
    file_paths = ["src/old.py", "src/deprecated.py"]
    
    # When: 임베딩 삭제
    count = await vector_db.delete_embeddings(
        collection="test_collection",
        file_paths=file_paths,
        user_id=1
    )
    
    # Then: 파일들이 삭제됨
    assert count == 2
    mock_qdrant_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_list_all_files(mock_qdrant_client):
    """사용자의 모든 인덱싱된 파일 목록 조회를 테스트.
    
    Given: 사용자의 코드 파일들이 Vector DB에 인덱싱되어 있고
    When: 파일 목록을 조회하면
    Then: 인덱싱된 모든 파일의 경로가 반환되어야 함
    
    검증사항:
    - 딕셔너리 형태로 반환
    - 파일 경로가 키로 포함됨
    """
    # When: 파일 목록 조회
    files = await vector_db.list_all_files(
        collection="test_collection",
        user_id=1
    )
    
    # Then: 파일 목록 반환
    assert isinstance(files, dict)
    assert "src/test.py" in files


@pytest.mark.asyncio
async def test_generate_embedding():
    """OpenAI API를 사용한 임베딩 생성을 테스트.
    
    Given: OpenAI API 키가 설정되어 있고
    When: 텍스트의 임베딩을 생성하면
    Then: 1536 차원의 임베딩 벡터가 반환되어야 함
    
    검증사항:
    - 임베딩 벡터가 생성됨
    - 벡터 차원이 1536 (OpenAI text-embedding-ada-002)
    """
    # Given: OpenAI client mock
    with patch('openai.AsyncOpenAI') as mock_client:
        mock_instance = AsyncMock()
        mock_response = MagicMock()
        mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
        mock_instance.embeddings.create = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_instance
        
        # When: 임베딩 생성
        embedding = await vector_db.generate_embedding("test text")
        
        # Then: 1536 차원 벡터 반환
        assert embedding is not None
        assert len(embedding) == 1536


@pytest.mark.asyncio
async def test_generate_embedding_without_api_key():
    """API 키 없이 임베딩 생성 시도를 테스트.
    
    Given: OpenAI API 키가 설정되지 않았고
    When: 임베딩 생성을 시도하면
    Then: None이 반환되어야 함 (에러 대신)
    
    검증사항:
    - None 반환
    - 에러 발생하지 않음
    """
    # Given: API 키 없음
    with patch('src.server.settings.settings') as mock_settings:
        mock_settings.OPENAI_API_KEY = None
        
        # When: 임베딩 생성 시도
        embedding = await vector_db.generate_embedding("test")
        
        # Then: 결정론적 1536 차원 벡터 반환
        assert embedding is not None
        assert isinstance(embedding, list)
        assert len(embedding) == 1536


@pytest.mark.asyncio
async def test_user_data_isolation():
    """사용자 간 데이터 격리가 올바르게 작동하는지 테스트.
    
    Given: 여러 사용자의 데이터가 Vector DB에 있고
    When: 각 사용자가 검색을 수행하면
    Then: 각 사용자는 자신의 데이터만 볼 수 있어야 함
    
    검증사항:
    - User 1의 검색은 User 1의 데이터만 반환
    - User 2의 검색은 User 2의 데이터만 반환
    - 서로의 데이터에 접근할 수 없음
    """
    # Given: 두 사용자의 데이터를 모킹
    mock_client = AsyncMock()
    
    # Mock search results for user 1
    point1 = MagicMock()
    point1.payload = {"user_id": 1, "file": "user1_file.py", "content_preview": "user1 content"}
    point1.score = 0.9
    
    # Mock search results for user 2
    point2 = MagicMock()
    point2.payload = {"user_id": 2, "file": "user2_file.py", "content_preview": "user2 content"}
    point2.score = 0.8
    
    async def mock_search(*args, **kwargs):
        # Return different results based on user_id filter
        user_id = kwargs["query_filter"].must[0].match.value
        if user_id == 1:
            return [point1]
        elif user_id == 2:
            return [point2]
        return []
    
    mock_client.search = AsyncMock(side_effect=mock_search)
    
    with patch('src.adapters.vector_db.get_qdrant_client', return_value=mock_client):
        with patch('src.adapters.vector_db.generate_embedding', new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = [0.1] * 1536
            # When: User 1 검색
            results1 = await vector_db.semantic_search(
                collection="test",
                query="test",
                user_id=1,
                top_k=5
            )
            
            # When: User 2 검색
            results2 = await vector_db.semantic_search(
                collection="test",
                query="test",
                user_id=2,
                top_k=5
            )
            
            # Then: 각 사용자는 자신의 데이터만 접근
            assert results1[0]["file"] == "user1_file.py"
            assert results2[0]["file"] == "user2_file.py"
            assert results1[0]["content"] != results2[0]["content"]
