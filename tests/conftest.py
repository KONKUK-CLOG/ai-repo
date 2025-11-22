"""Pytest configuration and fixtures.

이 모듈은 모든 테스트에서 공유되는 pytest fixture들을 정의합니다.
Fixture는 테스트 실행 전에 자동으로 설정되고 정리되는 재사용 가능한 컴포넌트입니다.

주요 Fixture:
- client: FastAPI 테스트 클라이언트
- mock_user: 테스트용 사용자 객체
- api_headers: API 키 인증 헤더
- mock_user_repo: 사용자 저장소 mock
- mock_openai_*: OpenAI API mock (임베딩, 채팅)
- mock_qdrant_client: Vector DB (Qdrant) mock
- mock_neo4j_driver: Graph DB (Neo4j) mock
- mock_github_api: GitHub OAuth API mock

각 fixture는 실제 외부 서비스를 호출하지 않고 더미 데이터를 반환하여
빠르고 안정적인 테스트를 가능하게 합니다.
"""
import pytest
from fastapi.testclient import TestClient
from src.server.main import app
from src.models.user import User
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Dict, Any


TEST_API_KEY = "test-api-key"


@pytest.fixture
def client():
    """FastAPI 테스트 클라이언트를 생성합니다.
    
    Returns:
        FastAPI TestClient: HTTP 요청을 시뮬레이션할 수 있는 테스트 클라이언트
        
    사용법:
        def test_endpoint(client):
            response = client.get("/healthz")
            assert response.status_code == 200
            
    설명:
        - 실제 HTTP 서버를 시작하지 않고 테스트
        - FastAPI 앱의 모든 엔드포인트 접근 가능
        - 동기 방식으로 API 테스트 가능
    """
    return TestClient(app)


@pytest.fixture
def mock_user():
    """테스트용 mock 사용자를 생성합니다.
    
    Returns:
        User: GitHub OAuth로 인증된 테스트 사용자 객체
        
    사용법:
        def test_with_user(mock_user):
            assert mock_user.id == 1
            assert mock_user.username == "testuser"
            
    설명:
        - GitHub ID: 12345678
        - Username: testuser
        - Email: testuser@example.com
        - Java 백엔드에서 발급된 API 키로 인증 (테스트에서는 더미 키 사용)
    """
    return User(
        id=1,
        github_id=12345678,
        username="testuser",
        email="testuser@example.com",
        avatar_url="https://avatars.githubusercontent.com/u/12345678",
    )


@pytest.fixture
def api_headers():
    """API 인증 헤더를 생성합니다.
    
    Args:
        mock_user: 테스트용 사용자 (자동 주입)
        
    Returns:
        Dict[str, str]: x-api-key 헤더가 포함된 딕셔너리
        
    사용법:
        def test_authenticated_endpoint(client, api_headers):
            response = client.get("/api/v1/commands", headers=api_headers)
            assert response.status_code == 200
            
    설명:
        - x-api-key 헤더에 API 키 포함
        - 인증이 필요한 엔드포인트 테스트 시 사용
        - 401 에러 없이 보호된 리소스 접근 가능
    """
    return {"x-api-key": TEST_API_KEY}


@pytest.fixture
def mock_user_repo(mock_user):
    """사용자 저장소(repository)를 mocking합니다.
    
    Args:
        mock_user: 테스트용 사용자 (자동 주입)
        
    Yields:
        Mock: UserRepository의 mock 객체
        
    설명:
        - Java 백엔드 호출 없이 사용자 정보를 반환
        - API 키 기반 인증 흐름을 테스트에서 간소화
    """
    with patch('src.server.deps.user_repo') as deps_repo, \
         patch('src.server.routers.auth.user_repo') as auth_repo:
        for repo in (deps_repo, auth_repo):
            repo.get_by_api_key = AsyncMock(return_value=mock_user)
            repo.get_by_id = AsyncMock(return_value=mock_user)
            repo.sync_github_user = AsyncMock(return_value=(mock_user, TEST_API_KEY))
        yield deps_repo


@pytest.fixture(autouse=True)
def _set_github_oauth_settings():
    """Ensure GitHub OAuth settings are present in test env.
    Prevents 500 on /auth/github/* due to missing credentials.
    """
    from src.server.settings import settings
    settings.GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID or "test_client_id"
    settings.GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET or "test_client_secret"
    settings.GITHUB_REDIRECT_URI = settings.GITHUB_REDIRECT_URI or "http://localhost:8000/auth/github/callback"


@pytest.fixture
def mock_openai_embeddings():
    """OpenAI 임베딩 생성 API를 mocking합니다.
    
    Yields:
        AsyncMock: 더미 임베딩 벡터를 반환하는 mock
        
    사용법:
        @pytest.mark.asyncio
        async def test_embedding(mock_openai_embeddings):
            from src.adapters.vector_db import generate_embedding
            embedding = await generate_embedding("test text")
            assert len(embedding) == 1536
            
    설명:
        - 실제 OpenAI API 호출 없이 테스트
        - 1536차원의 더미 벡터 반환 (text-embedding-ada-002 규격)
        - API 키 불필요, 비용 발생 없음
        - 빠른 테스트 실행
    """
    with patch('src.adapters.vector_db.generate_embedding', new_callable=AsyncMock) as mock_embed:
        # Return a 1536-dimensional dummy embedding
        mock_embed.return_value = [0.1] * 1536
        yield mock_embed


@pytest.fixture
def mock_openai_chat():
    """OpenAI Chat Completions API를 mocking합니다.
    
    Yields:
        AsyncMock: LLM 응답을 시뮬레이션하는 mock 객체
        
    사용법:
        def test_llm_agent(client, mock_openai_chat):
            response = client.post("/api/v1/llm/execute", 
                                    json={"prompt": "블로그 써줘"},
                                    headers={"x-api-key": TEST_API_KEY})
            assert response.status_code == 200
            
    설명:
        - 실제 LLM API 호출 없이 테스트
        - 미리 정의된 JSON 응답 반환
        - 툴 호출, 텍스트 생성 등 시뮬레이션
        - GPT-4, Claude 등 모든 모델을 동일하게 처리
        - 비용 발생 없음, 빠른 실행
    """
    from types import SimpleNamespace
    with patch('openai.AsyncOpenAI') as mock_client:
        # Create mock response with proper structure
        mock_message = MagicMock()
        mock_message.content = '{"title": "Test Article", "markdown": "# Test Content"}'
        mock_message.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4-turbo-preview"

        # Build namespaces with async create methods to avoid awaiting MagicMock
        async def chat_create(**kwargs):
            return mock_response

        async def embed_create(**kwargs):
            mock_embedding_data = MagicMock()
            mock_embedding_data.embedding = [0.1] * 1536
            mock_embedding_response = MagicMock()
            mock_embedding_response.data = [mock_embedding_data]
            return mock_embedding_response

        chat_ns = SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=chat_create)))
        embeddings_ns = SimpleNamespace(create=AsyncMock(side_effect=embed_create))
        mock_instance = SimpleNamespace(chat=chat_ns, embeddings=embeddings_ns)

        mock_client.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_qdrant_client():
    """Qdrant Vector DB 클라이언트를 mocking합니다.
    
    Yields:
        AsyncMock: Vector DB 작업을 시뮬레이션하는 mock 클라이언트
        
    사용법:
        @pytest.mark.asyncio
        async def test_vector_search(mock_qdrant_client):
            from src.adapters.vector_db import semantic_search
            results = await semantic_search("test_collection", "query", user_id=1)
            assert len(results) > 0
            
    설명:
        - 실제 Qdrant 서버 없이 테스트
        - search: 시맨틱 검색 결과 반환
        - upsert: 임베딩 저장 시뮬레이션
        - delete: 임베딩 삭제 시뮬레이션
        - scroll: 모든 문서 조회 시뮬레이션
        - 더미 검색 결과 (src/test.py, score=0.85)
    """
    mock_client = AsyncMock()
    
    # Mock search results with complete payload structure
    mock_point = MagicMock()
    mock_point.payload = {
        "user_id": 1,
        "file": "src/test.py",
        "content": "def test(): pass",  # Full content for semantic search
        "content_preview": "def test(): pass",
        "content_length": 100
    }
    mock_point.score = 0.85
    
    # Configure async methods
    mock_client.search = AsyncMock(return_value=[mock_point])
    mock_client.upsert = AsyncMock(return_value=None)
    mock_client.delete = AsyncMock(return_value=None)
    mock_client.scroll = AsyncMock(return_value=([mock_point], None))
    mock_client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    mock_client.create_collection = AsyncMock(return_value=None)
    
    with patch('src.adapters.vector_db.get_qdrant_client', return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_neo4j_driver():
    """Neo4j Graph DB 드라이버를 mocking합니다.
    
    Yields:
        AsyncMock: Graph DB 작업을 시뮬레이션하는 mock 드라이버
        
    사용법:
        @pytest.mark.asyncio
        async def test_graph_search(mock_neo4j_driver):
            from src.adapters.graph_db import search_related_code
            results = await search_related_code("test", user_id=1)
            assert len(results) > 0
            
    설명:
        - 실제 Neo4j 서버 없이 테스트
        - Cypher 쿼리 실행 시뮬레이션
        - session.run: 쿼리 결과 반환
        - 더미 결과 (test_function, type=function)
        - 함수, 클래스, 호출 관계 등 그래프 데이터 시뮬레이션
    """
    mock_driver = AsyncMock()
    mock_session = AsyncMock()
    
    # Mock query results with complete data structure
    mock_record = MagicMock()
    mock_record.__getitem__ = lambda self, key: {
        "entity_name": "test_function",
        "entity_type": "function",
        "file_path": "src/test.py",
        "file": "src/test.py",  # Add file field for compatibility
        "line_start": 10,
        "line_end": 20,
        "calls": ["helper_func"]
    }.get(key)
    
    # Async iterator for query results
    class _AsyncResult:
        def __init__(self, records):
            self._records = list(records)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self._records:
                return self._records.pop(0)
            raise StopAsyncIteration

    mock_session.run = AsyncMock(return_value=_AsyncResult([mock_record]))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock()
    
    mock_driver.session = MagicMock(return_value=mock_session)
    mock_driver.verify_connectivity = AsyncMock()
    
    with patch('src.adapters.graph_db.get_neo4j_driver', return_value=mock_driver):
        yield mock_driver


@pytest.fixture
def mock_tools():
    """Mock the remaining MCP tool run() methods.
    
    Yields:
        Dict of mocked tool run functions
    """
    with patch('src.mcp.tools.post_blog_article.run', new_callable=AsyncMock) as mock_blog:
        with patch('src.mcp.tools.search_vector_db.run', new_callable=AsyncMock) as mock_vector:
            with patch('src.mcp.tools.search_graph_db.run', new_callable=AsyncMock) as mock_graph:
                mock_blog.return_value = {
                    "success": True,
                    "article": {
                        "article_id": "test-123",
                        "url": "https://blog.example.com/test-123",
                        "published": True
                    }
                }
                mock_vector.return_value = {
                    "success": True,
                    "results": [
                        {"file": "src/test.py", "content_preview": "def foo(): pass", "score": 0.9}
                    ],
                    "total_results": 1,
                    "query": "테스트",
                    "top_k": 10
                }
                mock_graph.return_value = {
                    "success": True,
                    "results": [
                        {"file": "src/test.py", "entity_name": "Foo", "entity_type": "function"}
                    ],
                    "total_results": 1,
                    "query": "테스트",
                    "limit": 10
                }
                yield {
                    'blog': mock_blog,
                    'vector': mock_vector,
                    'graph': mock_graph
                }


@pytest.fixture
def mock_blog_api():
    """Mock blog API adapter.
    
    Yields:
        AsyncMock for blog_api.publish_article
    """
    with patch('src.adapters.blog_api.publish_article', new_callable=AsyncMock) as mock:
        mock.return_value = {
            "article_id": "test-123",
            "url": "https://blog.example.com/test-123",
            "published": True
        }
        yield mock


@pytest.fixture
def mock_github_api():
    """GitHub OAuth API를 mocking합니다.
    
    Yields:
        AsyncMock: GitHub API 응답을 시뮬레이션하는 mock 클라이언트
        
    사용법:
        def test_github_callback(client, mock_github_api):
            response = client.get("/auth/github/callback?code=test_code")
            assert response.status_code == 200
            assert "api_key" in response.json()
            
    설명:
        - 실제 GitHub API 호출 없이 테스트
        - OAuth 토큰 교환 시뮬레이션
        - 사용자 정보 조회 시뮬레이션
        - POST /login/oauth/access_token: 액세스 토큰 반환
        - GET /user: 사용자 정보 반환
        - 더미 사용자 (testuser, id=12345678)
    """
    with patch('httpx.AsyncClient') as mock_client:
        mock_instance = AsyncMock()
        
        # Mock access token response
        token_response = MagicMock()
        token_response.json.return_value = {"access_token": "gho_test_token"}
        
        # Mock user info response
        user_response = MagicMock()
        user_response.json.return_value = {
            "id": 12345678,
            "login": "testuser",
            "email": "testuser@example.com",
            "avatar_url": "https://avatars.githubusercontent.com/u/12345678"
        }
        
        mock_instance.post = AsyncMock(return_value=token_response)
        mock_instance.get = AsyncMock(return_value=user_response)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock()
        
        mock_client.return_value = mock_instance
        yield mock_instance
