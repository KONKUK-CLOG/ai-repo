"""Authentication endpoints for GitHub OAuth.

GitHub OAuth 2.0을 사용한 사용자 인증 엔드포인트입니다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📌 OAuth 핵심 개념 이해하기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Q: GITHUB_CLIENT_ID는 무엇인가?
A: 서비스(앱) 자체를 식별하는 ID입니다. 사용자별로 다른 것이 아닙니다!

비유: 카카오톡 앱 로그인
- CLIENT_ID: "이 앱은 카카오톡입니다" (앱 식별자, 1개)
- 사용자들: 김철수, 이영희, 박민수 (여러 명)

Q: 설정은 어떻게 하나?
A: 개발자/운영자가 서버 시작 전에 .env 파일에 한 번만 설정합니다.

예시:
    .env 파일:
        GITHUB_CLIENT_ID=Ov23liABCDEF123456        # ← 서비스 식별자 (1개)
        GITHUB_CLIENT_SECRET=secret_key_dont_share
        
    이후 모든 사용자가 이 하나의 OAuth 앱을 통해 로그인합니다.

Q: 여러 사용자는 어떻게 구분하나?
A: GitHub ID와 각자의 API 키로 구분합니다.

사용자 A → GitHub 로그인 → API 키: key-A 발급
사용자 B → GitHub 로그인 → API 키: key-B 발급
사용자 C → GitHub 로그인 → API 키: key-C 발급

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 OAuth 2.0 인증 플로우 (표준 Authorization Code Flow)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 클라이언트: GET /auth/github/login → GitHub로 리다이렉트
   └─ URL에 CLIENT_ID 포함 (이 서비스를 GitHub에 알림)

2. 사용자: GitHub에서 로그인 및 권한 승인
   └─ "Clog 앱이 당신의 GitHub 프로필 정보를 읽으려고 합니다. 허용하시겠습니까?"

3. GitHub: /auth/github/callback?code=xxx로 리다이렉트
   └─ 일회용 authorization code 발급

4. 서버: code를 access token으로 교환
   └─ CLIENT_ID + CLIENT_SECRET + code → access_token
   └─ 이 과정에서 서버 신원 검증 (CLIENT_SECRET 필요)

5. 서버: GitHub API에서 사용자 정보 조회
   └─ access_token으로 GitHub API 호출 → 사용자 프로필

6. 서버: DB에 사용자 upsert (없으면 생성, 있으면 업데이트)
   └─ github_id를 기준으로 사용자 식별
   └─ 신규 사용자면 새 API 키 생성, 기존 사용자면 last_login 업데이트

7. 서버: API 키 반환 (클라이언트는 이후 x-api-key 헤더에 사용)
   └─ 클라이언트는 이 API 키를 저장하여 모든 API 요청에 포함

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔐 보안 모델: Stateless Authentication
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- 서버는 세션을 저장하지 않음 (Stateless)
- 각 사용자는 고유한 API 키를 발급받음
- API 키는 x-api-key 헤더로 전송하여 인증
- 로그아웃 = 클라이언트에서 API 키 삭제

장점:
✓ 수평 확장 용이 (서버 간 세션 공유 불필요)
✓ 마이크로서비스 친화적
✓ 구현 단순
"""
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse, JSONResponse
from src.server.settings import settings
from src.server.schemas import AuthCallbackResponse, UserPublic
from src.adapters import github
from src.repositories.user_repo import user_repo
import logging
import urllib.parse

router = APIRouter(prefix="/auth/github", tags=["auth"])
logger = logging.getLogger(__name__)


@router.get("/login")
async def github_login():
    """GitHub OAuth 인증 시작.
    
    사용자를 GitHub 인증 페이지로 리다이렉트합니다.
    GitHub에서 인증 후 /auth/github/callback으로 돌아옵니다.
    
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🔍 OAuth Step 1: 인증 시작 (Authorization Request)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    이 엔드포인트의 역할:
    1. CLIENT_ID 확인 (서비스가 제대로 설정되었는지 검증)
    2. GitHub OAuth URL 생성
    3. 사용자를 GitHub 로그인 페이지로 리다이렉트
    
    중요: 이 함수는 사용자 인증이 필요 없음!
          누구나 로그인을 시도할 수 있어야 하기 때문입니다.
    
    Query Parameters:
        redirect_url: (Optional) 인증 후 돌아갈 클라이언트 URL
    
    Returns:
        RedirectResponse: GitHub OAuth 인증 페이지로 리다이렉트
        예시 URL: https://github.com/login/oauth/authorize?client_id=abc&redirect_uri=...
    
    Raises:
        HTTPException: 500 - GitHub OAuth가 설정되지 않음
        
        ⚠️ 이 에러가 발생한다면?
        → 개발자/운영자가 .env 파일에 GITHUB_CLIENT_ID를 설정하지 않은 것입니다.
        → 사용자 문제가 아니라 서버 설정 문제입니다!
        
        해결 방법:
        1. GitHub에서 OAuth App 등록
        2. .env 파일에 CLIENT_ID와 CLIENT_SECRET 추가
        3. 서버 재시작
    
    Example:
        >>> GET /auth/github/login
        >>> (Redirects to GitHub)
        >>> 
        >>> 사용자가 GitHub에서 로그인 후:
        >>> → GET /auth/github/callback?code=abc123
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1-1: CLIENT_ID 존재 확인
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 이 값은 서비스(앱) 자체를 식별합니다.
    # 모든 사용자가 같은 CLIENT_ID를 사용합니다.
    # 
    # 비유: 건물 주소 (모든 방문자가 같은 주소로 찾아옴)
    if not settings.GITHUB_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub OAuth not configured. Please set GITHUB_CLIENT_ID."
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1-2: GitHub OAuth URL 생성
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OAuth 표준 파라미터:
    # - client_id: 이 서비스가 누구인지 GitHub에 알림
    # - redirect_uri: 인증 후 돌아올 주소 (콜백 URL)
    # - scope: 요청하는 권한 범위
    params = {
        "client_id": settings.GITHUB_CLIENT_ID,        # 서비스 식별자 (1개)
        "redirect_uri": settings.GITHUB_REDIRECT_URI,  # 콜백 URL
        "scope": "read:user user:email",               # 사용자 정보 및 이메일 읽기 권한만
    }
    
    # 최종 URL 예시:
    # https://github.com/login/oauth/authorize?
    #   client_id=Ov23liABCDEF123456&
    #   redirect_uri=http://localhost:8000/auth/github/callback&
    #   scope=read:user+user:email
    github_auth_url = f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    
    logger.info(f"Redirecting to GitHub OAuth: {github_auth_url}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 1-3: 사용자를 GitHub로 리다이렉트
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 사용자는 GitHub 페이지에서:
    # 1. GitHub 계정으로 로그인
    # 2. "Clog 앱이 정보를 읽으려고 합니다" 승인
    # 3. 승인 후 자동으로 redirect_uri로 돌아옴
    return RedirectResponse(url=github_auth_url)


@router.get("/callback", response_model=AuthCallbackResponse)
async def github_callback(code: str):
    """GitHub OAuth callback 처리.
    
    GitHub에서 인증 후 돌아오는 엔드포인트입니다.
    OAuth code를 access token으로 교환하고, 사용자 정보를 조회하여
    DB에 저장한 후 API 키를 반환합니다.
    
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🔐 OAuth Step 2-7: 콜백 처리 (핵심!)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    이 함수가 OAuth의 가장 복잡하고 중요한 부분입니다.
    
    전체 흐름:
    Step 2: GitHub가 일회용 code와 함께 이 URL 호출
            예: /auth/github/callback?code=abc123xyz
    
    Step 3: code를 access_token으로 교환
            왜? code는 일회용이고 짧은 수명이므로
            장기 사용 가능한 access_token으로 바꿔야 함
            
            교환 시 필요:
            - CLIENT_ID: "나는 Clog 앱입니다"
            - CLIENT_SECRET: "이게 증거입니다" (비밀 키)
            - code: "사용자가 승인했습니다"
    
    Step 4: access_token으로 GitHub API 호출
            GET https://api.github.com/user
            Header: Authorization: Bearer {access_token}
            
            반환 정보:
            - id: GitHub 사용자 ID (예: 12345)
            - login: 사용자명 (예: "parkj")
            - email: 이메일
            - name: 이름
    
    Step 5: DB에 사용자 저장/업데이트
            github_id로 조회:
            - 없으면: 새 사용자 생성 + API 키 발급
            - 있으면: last_login 업데이트
    
    Step 6: 사용자별 API 키 반환
            이 API 키로 이후 모든 API 요청을 인증합니다.
    
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    💡 여러 사용자는 어떻게 구분되나?
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    사용자 A (github_id=12345):
      /login → GitHub 로그인 → code=abc → 처리 → api_key=key-A
    
    사용자 B (github_id=67890):
      /login → GitHub 로그인 → code=xyz → 처리 → api_key=key-B
    
    같은 CLIENT_ID를 사용하지만, GitHub가 각 사용자마다
    다른 code를 발급하고, 그 code로 조회한 사용자 정보가
    달라서 결국 다른 API 키를 받습니다!
    
    Args:
        code: GitHub OAuth authorization code (일회용, 10분 유효)
    
    Returns:
        AuthCallbackResponse: 인증 성공 응답
            - success: True
            - api_key: 사용자별 고유 API 키 (UUID 형식)
            - user: 사용자 공개 정보
            - message: 성공 메시지
    
    Raises:
        HTTPException:
            - 400: code 파라미터 누락
            - 500: Token 교환 실패 또는 사용자 정보 조회 실패
    
    Example:
        >>> # 사용자 A가 로그인
        >>> GET /auth/github/callback?code=abc123
        >>> Response: {
        >>>     "success": true,
        >>>     "api_key": "550e8400-e29b-41d4-a716-446655440000",
        >>>     "user": {
        >>>         "id": 1,
        >>>         "github_id": 12345,
        >>>         "username": "user_a"
        >>>     },
        >>>     "message": "Successfully authenticated as user_a"
        >>> }
        >>>
        >>> # 사용자 B가 로그인
        >>> GET /auth/github/callback?code=xyz789
        >>> Response: {
        >>>     "success": true,
        >>>     "api_key": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",  # 다른 키!
        >>>     "user": {
        >>>         "id": 2,
        >>>         "github_id": 67890,
        >>>         "username": "user_b"
        >>>     },
        >>>     "message": "Successfully authenticated as user_b"
        >>> }
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2-1: Code 파라미터 검증
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GitHub가 제대로 리다이렉트했다면 반드시 code가 있어야 함
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' parameter"
        )
    
    logger.info(f"Processing GitHub OAuth callback (code length: {len(code)})")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2-2: Code → Access Token 교환
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GitHub API 호출: POST https://github.com/login/oauth/access_token
    # Body:
    #   - client_id: Ov23liABCDEF123456 (서비스 식별)
    #   - client_secret: secret_key (서버 신원 증명)
    #   - code: abc123 (사용자가 승인했다는 증거)
    #
    # 응답: access_token=gho_abcdefgh123456...
    #
    # 왜 필요한가?
    # - code는 일회용이고 짧은 수명 (10분)
    # - access_token은 장기 사용 가능 (만료 없음 or 장기)
    # - CLIENT_SECRET으로 서버 신원 검증 (중간자 공격 방지)
    access_token = await github.exchange_code_for_token(code)
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to exchange code for access token"
        )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2-3: Access Token으로 사용자 정보 조회
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # GitHub API 호출: GET https://api.github.com/user
    # Header: Authorization: Bearer gho_abcdefgh123456...
    #
    # 응답 예시:
    # {
    #   "id": 12345,              ← 고유 식별자 (중요!)
    #   "login": "parkj",         ← 사용자명
    #   "email": "parkj@example.com",
    #   "name": "Park J",
    #   "avatar_url": "https://..."
    # }
    #
    # 여기서 각 사용자가 구분됩니다!
    # - 사용자 A의 code → 사용자 A의 token → 사용자 A의 정보
    # - 사용자 B의 code → 사용자 B의 token → 사용자 B의 정보
    user_info = await github.get_user_info(access_token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch user information from GitHub"
        )
    
    logger.info(f"GitHub user authenticated: {user_info['login']} (id={user_info['id']})")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2-4: DB에 사용자 저장/업데이트 (Upsert 패턴)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # github_id를 기준으로 조회:
    #
    # 시나리오 1: 신규 사용자 (github_id가 DB에 없음)
    #   → INSERT:
    #     - github_id: 12345
    #     - username: "parkj"
    #     - api_key: UUID 생성 (550e8400-e29b-41d4...)
    #     - created_at: 현재 시각
    #     - last_login: 현재 시각
    #
    # 시나리오 2: 기존 사용자 (github_id가 DB에 있음)
    #   → UPDATE:
    #     - last_login: 현재 시각 (업데이트)
    #     - username, email, name: 최신 정보로 업데이트 (GitHub에서 변경 가능)
    #     - api_key: 유지 (변경하지 않음!)
    #
    # 왜 api_key를 새로 발급하지 않나?
    # → 기존 사용자가 로그인할 때마다 API 키가 바뀌면
    #   클라이언트가 계속 새 키를 저장해야 해서 불편함
    user = await user_repo.upsert(
        github_id=user_info["id"],
        username=user_info["login"],
        email=user_info.get("email"),
        name=user_info.get("name")
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2-5: 응답 데이터 준비
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UserPublic: 보안을 위해 API 키는 제외한 공개 정보만
    #             (응답에서는 api_key를 별도 필드로 전달)
    user_public = UserPublic(
        id=user.id,
        github_id=user.github_id,
        username=user.username,
        email=user.email,
        name=user.name,
        created_at=user.created_at,
        last_login=user.last_login
    )
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # Step 2-6: 최종 응답 반환 (API 키 포함!)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 클라이언트는 이 api_key를 저장하고, 이후 모든 API 요청에
    # x-api-key 헤더로 포함해야 합니다.
    #
    # 예시:
    # fetch('/api/v1/diffs/apply', {
    #   headers: {
    #     'x-api-key': '550e8400-e29b-41d4-a716-446655440000',
    #     'Content-Type': 'application/json'
    #   },
    #   body: JSON.stringify({...})
    # })
    response = AuthCallbackResponse(
        success=True,
        api_key=user.api_key,  # ← 사용자별 고유 API 키
        user=user_public,
        message=f"Successfully authenticated as {user.username}"
    )
    
    logger.info(f"User {user.username} (id={user.id}) authenticated successfully")
    
    return response


@router.get("/logout")
async def github_logout():
    """로그아웃 엔드포인트.
    
    현재는 stateless 인증(API 키 기반)이므로 서버에서 할 일이 없습니다.
    클라이언트가 API 키를 삭제하면 됩니다.
    
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    🚪 Stateless 로그아웃
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    
    전통적인 세션 기반 인증:
    - 서버가 세션 ID를 메모리/Redis에 저장
    - 로그아웃 시 서버에서 세션 삭제 필요
    
    현재 시스템 (Stateless):
    - 서버는 API 키 외에 아무것도 저장하지 않음
    - 로그인 상태를 추적하지 않음
    - 로그아웃 = 클라이언트가 API 키 삭제
    
    장점:
    ✓ 서버 확장이 쉬움 (세션 공유 불필요)
    ✓ 서버 재시작해도 사용자 로그인 유지
    ✓ 분산 시스템에 적합
    
    단점:
    ✗ API 키 유출 시 강제 로그아웃 어려움
      (해결: DB에서 api_key 변경하는 엔드포인트 추가 가능)
    
    클라이언트 구현 예시:
    ```javascript
    // 로그아웃
    localStorage.removeItem('api_key');
    // 또는
    sessionStorage.clear();
    ```
    
    Returns:
        메시지: 로그아웃 안내
    
    Example:
        >>> GET /auth/github/logout
        >>> Response: {
        >>>     "message": "Logout successful. Please delete your API key from the client.",
        >>>     "note": "This is a stateless authentication system. The server does not track sessions."
        >>> }
    """
    # Stateless 시스템이므로 서버는 아무 작업도 하지 않음
    # 클라이언트가 API 키를 삭제하는 것으로 충분
    return {
        "message": "Logout successful. Please delete your API key from the client.",
        "note": "This is a stateless authentication system. The server does not track sessions."
    }

