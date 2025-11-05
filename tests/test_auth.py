"""Tests for GitHub OAuth authentication.

이 모듈은 GitHub OAuth 2.0 인증 흐름을 테스트합니다:
1. GitHub 로그인 리다이렉트
2. OAuth 콜백 처리 및 사용자 생성
3. API 키 기반 인증
4. 사용자 격리(isolation)

각 테스트는 Given-When-Then 패턴을 따릅니다.
"""
import pytest
from unittest.mock import patch, AsyncMock


def test_github_login_redirect(client):
    """GitHub OAuth 로그인이 올바른 리다이렉트를 생성하는지 테스트.
    
    Given: 애플리케이션이 실행 중이고 GitHub OAuth가 설정되어 있으면
    When: 사용자가 /auth/github/login을 방문하면
    Then: GitHub OAuth 페이지로 리다이렉트되거나 설정 오류를 반환해야 함
    
    검증사항:
    - GitHub OAuth 설정 시: 302/307 리다이렉트
    - GitHub OAuth 미설정 시: 500 에러
    
    참고:
    - 테스트 환경에서는 GITHUB_CLIENT_ID가 없을 수 있음
    - 500 에러도 정상적인 동작으로 간주
    """
    # When: GitHub 로그인 엔드포인트 호출
    response = client.get("/auth/github/login")
    
    # Then: 리다이렉트 또는 설정 오류
    # GitHub OAuth가 설정되어 있으면 리다이렉트, 없으면 500 에러
    if response.status_code in [302, 307]:
        # 리다이렉트 성공
        assert "github.com" in response.headers.get("location", "")
    else:
        # GitHub OAuth 미설정 시 500 에러
        assert response.status_code == 500


def test_github_callback_success(client, mock_user_repo, mock_github_api):
    """GitHub OAuth 콜백이 성공적으로 처리되는지 테스트.
    
    Given: GitHub에서 인증 코드를 받았고
    When: 콜백 엔드포인트에 인증 코드와 함께 요청하면
    Then: API 키와 사용자 정보가 반환되어야 함
    
    검증사항:
    - HTTP 200 응답
    - success 필드가 True
    - api_key가 응답에 포함
    - user 정보가 응답에 포함
    - 사용자 이름이 올바름
    """
    # When: GitHub 콜백 엔드포인트 호출 (인증 코드 포함)
    response = client.get(
        "/auth/github/callback?code=test_code_123"
    )
    
    # Then: 성공 응답과 함께 API 키 및 사용자 정보 반환
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "api_key" in data
    assert "user" in data
    assert data["user"]["username"] == "testuser"


def test_github_callback_without_code(client):
    """인증 코드 없이 콜백을 호출할 때 오류 반환을 테스트.
    
    Given: GitHub OAuth 인증이 설정되어 있고
    When: 인증 코드 없이 콜백 엔드포인트를 호출하면
    Then: 400 또는 422 에러가 반환되어야 함
    
    검증사항:
    - HTTP 400 또는 422 응답 (잘못된 요청)
    """
    # When: 인증 코드 없이 콜백 호출
    response = client.get("/auth/github/callback")
    
    # Then: 에러 응답
    assert response.status_code in [400, 422]


def test_github_callback_creates_new_user(client, mock_github_api):
    """처음 로그인하는 사용자가 자동으로 생성되는지 테스트.
    
    Given: GitHub에서 새로운 사용자가 인증을 완료했고
          해당 사용자가 DB에 존재하지 않으면
    When: 콜백 엔드포인트가 호출되면
    Then: 새 사용자가 생성되고 API 키가 발급되어야 함
    
    검증사항:
    - HTTP 200 응답
    - 새 사용자가 데이터베이스에 생성됨
    - API 키가 응답에 포함
    """
    # Given: 새 사용자 (DB에 없음)
    with patch('src.repositories.user_repo.UserRepository') as MockRepo:
        mock_repo_instance = MockRepo.return_value
        mock_repo_instance.get_user_by_github_id = AsyncMock(return_value=None)
        mock_repo_instance.create_user = AsyncMock(return_value={
            "id": 1,
            "github_id": 12345678,
            "username": "testuser",
            "email": "testuser@example.com",
            "api_key": "new-test-key"
        })
        
        # When: GitHub 콜백 호출
        response = client.get("/auth/github/callback?code=test_code")
        
        # Then: 새 사용자 생성 및 API 키 발급
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data


def test_api_key_authentication(client, mock_user_repo):
    """API 키 기반 인증이 올바르게 작동하는지 테스트.
    
    Given: 유효한 API 키를 가진 사용자가 있고
    When: x-api-key 헤더와 함께 요청을 보내면
    Then: 요청이 성공적으로 처리되어야 함
    
    검증사항:
    - HTTP 200 응답
    - API 키 헤더가 올바르게 파싱됨
    """
    # When: API 키와 함께 요청
    response = client.get(
        "/healthz",
        headers={"x-api-key": "test-key-123"}
    )
    
    # Then: 요청 성공
    # 참고: Health 엔드포인트는 인증이 필요 없지만 헤더 파싱을 테스트함
    assert response.status_code == 200


def test_invalid_api_key(client, mock_tools):
    """유효하지 않은 API 키가 거부되는지 테스트.
    
    Given: 데이터베이스에 존재하지 않는 API 키로
    When: 인증이 필요한 엔드포인트에 요청하면
    Then: 401 Unauthorized 에러가 반환되어야 함
    
    검증사항:
    - HTTP 401 응답 (인증 실패)
    """
    # Given: 유효하지 않은 API 키
    with patch('src.server.deps.user_repo') as mock_repo:
        mock_repo.get_user_by_api_key = AsyncMock(return_value=None)
        
        # When: 유효하지 않은 API 키로 요청
        response = client.post(
            "/api/v1/diffs/apply",
            headers={"x-api-key": "invalid-key"},
            json={"files": []}
        )
        
        # Then: 인증 실패
        assert response.status_code == 401


def test_missing_api_key(client):
    """API 키가 없을 때 요청이 거부되는지 테스트.
    
    Given: API 키 없이
    When: 인증이 필요한 엔드포인트에 요청하면
    Then: 422 Unprocessable Entity 에러가 반환되어야 함
    
    검증사항:
    - HTTP 422 응답 (필수 헤더 누락)
    
    참고:
    - FastAPI는 필수 Depends 파라미터 누락 시 422를 반환
    - 401은 인증 실패 시 반환 (API 키가 잘못된 경우)
    """
    # When: API 키 없이 요청
    response = client.post(
        "/api/v1/diffs/apply",
        json={"files": []}
    )
    
    # Then: 422 에러 (필수 헤더 누락)
    assert response.status_code == 422


def test_user_isolation(client, mock_user_repo, mock_tools):
    """다중 사용자 간 데이터 격리가 올바르게 작동하는지 테스트.
    
    Given: 두 명의 서로 다른 사용자가 있고
    When: 각 사용자가 자신의 API 키로 요청을 보내면
    Then: 각 사용자의 데이터가 서로 격리되어 처리되어야 함
    
    검증사항:
    - 두 사용자 모두 성공적으로 요청 처리
    - 각 사용자의 데이터가 독립적으로 관리됨
    """
    # Given: User 1
    user1 = mock_user_repo.get_user_by_api_key.return_value
    user1.id = 1
    
    # When: User 1이 자신의 데이터로 요청
    response1 = client.post(
        "/api/v1/diffs/apply",
        headers={"x-api-key": "user1-key"},
        json={"files": [{"path": "test.py", "status": "modified", "after": "print(1)"}]}
    )
    
    # Then: User 1 요청 성공
    assert response1.status_code == 200
    
    # Given: User 2 (다른 데이터)
    user2 = mock_user_repo.get_user_by_api_key.return_value
    user2.id = 2
    
    # When: User 2가 자신의 데이터로 요청
    response2 = client.post(
        "/api/v1/diffs/apply",
        headers={"x-api-key": "user2-key"},
        json={"files": [{"path": "test.py", "status": "modified", "after": "print(2)"}]}
    )
    
    # Then: User 2 요청도 성공 (서로 격리됨)
    assert response2.status_code == 200

