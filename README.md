# TS-LLM-MCP Bridge

FastAPI + MCP 서버 프로젝트. TypeScript 클라이언트가 보낸 코드 증분(diff)과 LLM 명령을 Python 서버가 처리하며, 동일 기능을 MCP(Model Context Protocol) 툴로도 노출합니다.

## ✨ 주요 특징

- **🔐 다중 사용자 지원**: GitHub OAuth 2.0 (Java Auth 서버) + JWT 기반 인증
- **🔑 사용자별 JWT**: TS 클라이언트가 Java Auth 서버에서 받은 JWT를 Python 서버로 전달
- **🛡️ 서비스 간 JWT**: ServiceTokenManager가 Java ↔ Python 서버 간 토큰을 자동 발급/갱신
- **LLM SSE**: `POST /internal/v1/llm/execute/stream`으로 진행 단계를 `text/event-stream`으로 전송 (기존 JSON 엔드포인트 유지)
- **병렬 툴 실행**: 1차 LLM이 여러 `tool_calls`를 반환하면 동일 요청 안에서 `asyncio.gather`로 동시 실행한 뒤, 2차 LLM이 결과를 종합합니다.
- **Idempotency 지원**: `x-idempotency-key` 헤더로 중복 방지
- **MCP 툴 노출**: LLM이 안전하게 호출할 수 있는 MCP 프로토콜 지원
- **어댑터 패턴**: 외부 서비스(블로그, Vector DB, Graph DB, GitHub OAuth)를 어댑터로 분리
- **WAL (Write-Ahead Log)**: 모든 업데이트를 로그에 먼저 기록, 실패 시 자동 복구 (content 별도 파일 저장)
- **백그라운드 스케줄러**: 5분마다 WAL 복구, 1일마다 WAL 정리 (클라이언트 주도 동기화)
- **Vector DB 통합**: Qdrant를 사용한 시맨틱 검색 (OpenAI 임베딩)
- **Graph DB 통합**: Neo4j를 사용한 코드 관계 추적 (함수 호출, 임포트 등)

## 🏗️ 아키텍처

### Before (Single User)
```
Client → API (single API key) → Vector/Graph DB (no isolation)
```

### After (Multi-User) ✅
```
TS Client ── GitHub OAuth ── Java Auth Server
   │                 │
   └──JWT (user)─────┘
        │
Python API (JWT 검증만 수행)
        │
Vector/Graph DB (filtered by user_id)
```

**데이터 격리**:
- Vector DB: `user_id` 필드로 필터링
- Graph DB: 모든 노드에 `user_id` 속성
- WAL: 로그 엔트리에 `user_id` 포함

### 🔐 인증 흐름 요약
1. **TS ↔ Java**: GitHub OAuth + 사용자 JWT 발급 (Python은 관여하지 않음)
2. **TS → Python**: `Authorization: Bearer <사용자 JWT>` 헤더로 요청
3. **Python**: JWKS 공개키로 JWT 검증만 수행 (`verify_jwt`)
4. **Java → Python**: 내부 API 호출 시 서비스 전용 JWT 사용 (`verify_service_jwt`)
5. **Python → Java**: 사용자 요청은 전달받은 JWT를 그대로 전달, 시스템 작업은 서비스 JWT 사용

> `/auth/github/*` 엔드포인트는 더 이상 제공되지 않으며, GitHub 로그인은 TS ↔ Java 서버 사이에서만 처리됩니다.

### 🛡️ 서비스 간 JWT

| 방향 | 인증 방식 |
| --- | --- |
| TS → Python | 사용자 JWT (`Authorization: Bearer <user_jwt>`) |
| Python → Java (시스템 작업) | 서비스 JWT (ServiceTokenManager 자동 발급/갱신) |
| Java → Python (내부 API) | 서비스 JWT (`get_java_service_identity` → `verify_service_jwt`) |

- 서비스 JWT는 Java Auth 서버가 발급합니다.
- Python 서버는 `JAVA_BACKEND_SERVICE_JWT_*` 환경 변수로 검증 파라미터를 설정합니다.
- 내부 라우트(예: `/api/v1/admin/*`)는 `get_java_service_identity` 의존성으로 보호됩니다.

#### ServiceTokenManager

- FastAPI 시작 시 `ServiceTokenManager`가 Java Auth 서버에 `client_id/secret`로 토큰을 요청하고 만료 전에 자동 갱신합니다.
- `JAVA_BACKEND_SERVICE_JWT`가 주어지면 초기 토큰으로 사용하며, 자격 증명이 있을 경우 주기적으로 교체합니다.
- 모든 Python → Java 호출(`src/adapters/java_backend.py`)은 매니저를 통해 `Authorization: Bearer <service token>`을 부착하고, 401 응답 시 즉시 토큰을 새로 받아 한 번 재시도합니다.
- VS Code 확장은 기존처럼 Java Auth 서버에서 사용자 JWT를 발급받아 Python 서버 호출 시 헤더로 전달하면 됩니다.

## 프로젝트 구조

```
ts-llm-mcp-bridge/
├─ src/
│  ├─ models/             # 데이터 모델 (NEW)
│  │  └─ user.py         # User 모델
│  ├─ repositories/       # 데이터 저장소 (NEW)
│  │  └─ user_repo.py    # User repository (SQLite)
│  ├─ server/             # FastAPI 서버
│  │  ├─ main.py         # 앱 엔트리 포인트 + 백그라운드 스케줄러
│  │  ├─ settings.py     # 환경 설정 (JWT/JWKS)
│  │  ├─ deps.py         # 의존성 주입 (get_current_user / get_java_service_identity)
│  │  ├─ schemas.py      # Pydantic 스키마 (User schemas 추가)
│  │  └─ routers/        # API 라우터
│  │     ├─ auth.py      # Auth namespace placeholder (TS ↔ Java에서 처리)
│  │     ├─ health.py    # 헬스체크
│  │     ├─ diffs.py     # Diff 적용 (WAL 통합, 다중 사용자 지원)
│  │     ├─ agent.py     # LLM 에이전트 (다중 사용자 지원)
│  │     └─ commands.py  # 명령 실행 (다중 사용자 지원)
│  ├─ adapters/          # 외부 서비스 어댑터
│  │  ├─ blog_api.py     # 블로그 API
│  │  ├─ vector_db.py    # Qdrant Vector DB (user_id 지원)
│  │  ├─ graph_db.py     # Neo4j Graph DB (user_id 지원)
│  │  └─ github.py       # GitHub (OAuth 추가)
│  ├─ background/        # 백그라운드 작업
│  │  ├─ wal.py         # Write-Ahead Log (user_id 지원)
│  │  ├─ scheduler.py   # APScheduler
│  │  └─ tasks.py       # 주기적 작업 (WAL 복구, 정리)
│  └─ mcp/               # MCP 서버 및 툴
│     ├─ server.py       # stdio JSON-RPC 서버
│     └─ tools/          # MCP 툴들
│        ├─ post_blog_article.py
│        ├─ search_vector_db.py
│        └─ search_graph_db.py
├─ data/                 # 데이터 파일 (git ignored)
│  ├─ users.db          # 사용자 DB (SQLite, NEW)
│  ├─ wal.jsonl         # WAL 메타데이터
│  └─ wal_content/      # WAL content 파일들
├─ tests/                # 테스트
├─ requirements.txt      # Python 의존성
├─ Dockerfile           # Docker 이미지
└─ README.md
```

## AWS Lambda (LLM 실행만)

- 핸들러: [`src/lambda_handler.py`](src/lambda_handler.py) — `Mangum`으로 FastAPI 앱을 감싸며 `lifespan="off"`로 lifespan(스케줄러·ServiceTokenManager)은 실행하지 않습니다.
- 로컬/EC2에서 백그라운드 작업이 필요하면 `ENABLE_BACKGROUND_TASKS=true`(기본). Lambda에서는 설정하지 않아도 lifespan이 꺼져 스케줄러는 시작되지 않습니다; 명시적으로 끄려면 `ENABLE_BACKGROUND_TASKS=false`.
- **채팅 히스토리**: Java가 NoSQL에서 불러 `LLMExecuteRequest.history`에 넣어 전달합니다.
- **SSE**: `POST /internal/v1/llm/execute/stream` — `event: progress` / `event: complete` / `event: error`. API Gateway는 응답 버퍼링으로 스트림이 끊길 수 있어, 배포 후 청크 전달을 확인하세요. Lambda Function URL의 응답 스트리밍을 검토하세요.

### 코드베이스 검색 (MongoDB)

LLM 툴 `search_codebase`는 **Motor**로 MongoDB에 직접 접속합니다. Lambda/EC2에서는 URI와 네트워크(VPC Endpoint, Atlas IP allowlist 등)를 맞추세요.

- `CODEBASE_MONGO_URI`: 연결 문자열(없으면 툴이 `success: false`로 안내).
- `CODEBASE_MONGO_DB` / `CODEBASE_MONGO_COLLECTION`: 기본값 `clog` / `codebase_chunks`.
- `CODEBASE_MONGO_USER_ID_FIELD`, `CODEBASE_MONGO_PATH_FIELD`, `CODEBASE_MONGO_CONTENT_FIELD`: 문서 필드명.
- `CODEBASE_MONGO_PREVIEW_MAX_CHARS`: 응답 본문 미리보기 길이 상한.

예상 문서 형태: `{ "user_id": 1, "path": "src/foo.py", "content": "..." }`. 검색은 해당 사용자의 문서만 대상으로, 본문에 대한 대소문자 무시 부분 일치(`$regex`, 검색어는 `re.escape`)입니다. 데이터가 크면 인덱스나 Atlas Search 도입을 검토하세요.

## 🚀 빠른 시작 (다중 사용자)

### 1. Java Auth 서버 준비

- GitHub OAuth 플로우와 사용자 JWT 발급은 **Java 백엔드**가 담당합니다.
- TS 클라이언트는 Java Auth 서버에서 JWT를 받아 로컬에 저장합니다.
- Python 서버에는 **JWKS URL**과 **issuer/audience** 정보만 제공하면 됩니다.

### 2. 환경 변수 설정

`.env` 파일 생성:
```bash
# Java Auth 서버가 제공하는 JWKS 엔드포인트
JAVA_BACKEND_JWKS_URL=https://java-backend.example.com/.well-known/jwks.json
JAVA_BACKEND_JWT_ISSUER=https://java-backend.example.com
JAVA_BACKEND_JWT_AUDIENCE=ts-llm-mcp

# 서비스 간 JWT (자동 갱신)
JAVA_BACKEND_SERVICE_CLIENT_ID=python-api
JAVA_BACKEND_SERVICE_CLIENT_SECRET=super-secret
JAVA_BACKEND_SERVICE_JWT_SCOPE=internal-api
JAVA_BACKEND_SERVICE_JWT_REFRESH_PATH=/api/v1/auth/service-jwt
# (선택) 초기 토큰 (refresh 미사용 시)
JAVA_BACKEND_SERVICE_JWT=<static-service-token>
JAVA_BACKEND_SERVICE_JWT_AUDIENCE=python-internal
JAVA_BACKEND_SERVICE_JWT_ISSUER=https://java-backend.example.com

# OpenAI (임베딩 생성용)
OPENAI_API_KEY=your_openai_api_key
```

### 3. 서버 실행

```bash
pip install -r requirements.txt
uvicorn src.server.main:app --reload
```

### 4. API 호출

TS 클라이언트에서 받은 사용자 JWT를 그대로 전달합니다.

```bash
curl -H "Authorization: Bearer YOUR_USER_JWT" \
     http://localhost:8000/api/v1/diffs/apply \
     -H "Content-Type: application/json" \
     -d '{"files": [...]}'
```

## API 엔드포인트

### 인증 (Authentication)

> Python 서버는 더 이상 GitHub OAuth 엔드포인트를 노출하지 않습니다.  
> 로그인/토큰 발급은 자바 Auth 서버가 담당하며, Python 서버는 `Authorization: Bearer <JWT>` 헤더를 검증만 수행합니다.

### 헬스체크

- `GET /healthz` - 기본 헬스체크
- `GET /readyz` - 준비 상태 체크

### Diff 적용 (WAL 통합)

- `POST /api/v1/diffs/apply` - 코드 증분을 벡터/그래프 인덱스에 증분 반영
  - 모든 업데이트는 먼저 WAL에 기록
  - Vector DB (Qdrant)에 임베딩 생성 및 Upsert
  - Graph DB (Neo4j)에 코드 관계 추적
  - 실패 시 백그라운드에서 자동 재시도

**입력 형식 (2가지 중 선택)**:

1. **Unified 패치**:
```json
{
  "unified": "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,3 @@\n-old\n+new"
}
```

2. **Files 배열**:
```json
{
  "files": [
    {
      "path": "src/main.py",
      "status": "modified",
      "before": "print('hello')",
      "after": "print('hello world')"
    }
  ]
}
```

### 명령 실행 (개발 전용)

⚠️ **개발 환경에서만 사용하세요** (`ENABLE_DIRECT_TOOLS=true`)

- `GET /api/v1/commands` - 사용 가능한 명령(툴) 스키마 조회
- `POST /api/v1/commands/execute` - 고수준 명령(툴) 실행 (직접 툴 지정)

**명령 실행 예시**:
```json
{
  "name": "post_blog_article",
  "params": {
    "title": "My Article",
    "markdown": "# Hello World"
  }
}
```

### 관리자 엔드포인트

- `POST /api/v1/admin/wal-recovery` - 수동으로 WAL 복구 실행
- `POST /api/v1/admin/wal-cleanup` - 수동으로 WAL 정리 실행
- `GET /api/v1/admin/wal-stats` - WAL 통계 조회

**프로덕션에서는 LLM 에이전트만 사용하세요** 👇

### LLM 에이전트 (자연어 명령) 🤖

- `POST /api/v1/llm/execute` - 자연어 명령을 LLM이 해석하고 적절한 툴 실행
- **OpenAI GPT-4를 사용하여 실제로 동작합니다**
- API 키가 없으면 키워드 기반 폴백 로직 사용

**LLM 에이전트 실행 예시**:
```json
{
  "prompt": "코드 변경사항을 인덱스에 반영하고, 변경 내용을 요약해서 블로그에 올려줘",
  "context": {
    "diff": {
      "files": [
        {
          "path": "src/main.py",
          "status": "modified"
        }
      ]
    }
  },
  "model": "claude-3-5-sonnet"
}
```

**차이점**:
- `/api/v1/commands/execute`: TS가 **어떤 툴을 사용할지 직접 지정**
- `/api/v1/llm/execute`: **LLM이 자율적으로 툴을 선택하고 실행**

## 환경 변수

`.env` 파일을 생성하고 다음 변수들을 설정하세요:

```env
# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Java Auth / JWT 검증
JAVA_BACKEND_BASE_URL=https://java-backend.example.com
JAVA_BACKEND_JWKS_URL=https://java-backend.example.com/.well-known/jwks.json
JAVA_BACKEND_JWT_ISSUER=https://java-backend.example.com
JAVA_BACKEND_JWT_AUDIENCE=ts-llm-mcp

# 서비스 간 JWT (Java ↔ Python)
JAVA_BACKEND_SERVICE_JWT=<static-service-token>         # 선택: 정적 토큰
JAVA_BACKEND_SERVICE_JWT_REFRESH_PATH=/api/v1/auth/service-jwt
JAVA_BACKEND_SERVICE_JWT_ISSUER=https://java-backend.example.com
JAVA_BACKEND_SERVICE_JWT_AUDIENCE=python-internal
JAVA_BACKEND_SERVICE_JWT_ALGORITHMS=RS256

# GitHub (git 작업용)
GITHUB_TOKEN=your-github-token

# Blog API
BLOG_API_URL=https://api.example.com/blog
BLOG_API_KEY=your-blog-api-key

# Vector Database (Qdrant)
VECTOR_DB_URL=http://localhost:6333
VECTOR_DB_COLLECTION=code_embeddings
EMBED_BATCH_SIZE=100

# Graph Database (Neo4j)
GRAPH_DB_URL=bolt://localhost:7687
GRAPH_DB_USER=neo4j
GRAPH_DB_PASSWORD=your-graph-db-password

# LLM API (OpenAI)
OPENAI_API_KEY=your-openai-api-key
DEFAULT_LLM_MODEL=gpt-4-turbo-preview
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# Feature Flags
ENABLE_DIRECT_TOOLS=false  # true: 개발 환경에서만 활성화

# Limits
MAX_DIFF_BYTES=10485760  # 10MB
```

> ⚠️ GitHub OAuth 관련 환경 변수(`GITHUB_CLIENT_ID` 등)는 **Java Auth 서버 측**에서만 필요합니다. Python 서버는 JWKS 정보와 서비스 JWT 설정만 알면 됩니다.

### ⚠️ 중요 변경사항

- **Python 서버는 JWT 검증만 수행**: 사용자 인증/토큰 발급은 Java Auth 서버가 담당
- **서비스 간 JWT 필요**: Java → Python 내부 API 호출 시 Bearer 토큰 필수

## 설치 및 실행

### 로컬 개발

1. **의존성 설치**:
```bash
pip install -r requirements.txt
```

2. **환경 변수 설정**:
```bash
# .env 파일 생성
cat > .env << 'EOF'
JAVA_BACKEND_BASE_URL=https://java-backend.example.com
JAVA_BACKEND_JWKS_URL=https://java-backend.example.com/.well-known/jwks.json
JAVA_BACKEND_JWT_ISSUER=https://java-backend.example.com
JAVA_BACKEND_JWT_AUDIENCE=ts-llm-mcp
JAVA_BACKEND_SERVICE_JWT=<static-service-token>
OPENAI_API_KEY=your_openai_api_key
EOF
```

> GitHub OAuth App 설정은 Java Auth 서버 측에서만 필요합니다.

**OpenAI API 키 (선택사항)**:
- [OpenAI API Keys](https://platform.openai.com/api-keys)에서 키 발급
- 임베딩 생성 및 LLM 에이전트 사용 시 필요
- 키가 없으면 일부 기능만 사용 가능

**개발 환경 설정**:
```env
ENABLE_DIRECT_TOOLS=true  # 개발 시 툴 직접 테스트
```
- ⚠️ 프로덕션에서는 `false`로 설정 (기본값)

3. **서버 실행**:
```bash
uvicorn src.server.main:app --host 0.0.0.0 --port 8000 --reload
```

4. **API 문서 접속**:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker 실행

1. **이미지 빌드**:
```bash
docker build -t ts-llm-mcp-bridge .
```

2. **컨테이너 실행**:
```bash
docker run -p 8000:8000 --env-file .env ts-llm-mcp-bridge
```

## 테스트

```bash
# 전체 테스트 실행
pytest

# 상세 출력
pytest -v

# 특정 테스트 파일
pytest tests/test_health.py
```

## 사용 예시

### 1. 사용자 JWT 전달

TS 클라이언트가 Java Auth 서버에서 받은 JWT를 사용합니다.

```bash
export USER_JWT="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### 2. API 호출 (JWT 기반)

```bash
# 헬스체크
curl http://localhost:8000/healthz

# Diff 적용 (사용자별로 격리됨)
curl -X POST http://localhost:8000/api/v1/diffs/apply \
  -H "Authorization: Bearer $USER_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "path": "src/main.py",
        "status": "modified",
        "after": "print(\"hello world\")"
      }
    ]
  }'

# 명령 목록 조회
curl -H "Authorization: Bearer $USER_JWT" \
     http://localhost:8000/api/v1/commands

# 블로그 포스트 발행
curl -X POST http://localhost:8000/api/v1/commands/execute \
  -H "Authorization: Bearer $USER_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "post_blog_article",
    "params": {
      "title": "Test Article",
      "markdown": "# Hello World"
    }
  }'

# LLM 에이전트로 자연어 명령 실행
curl -X POST http://localhost:8000/api/v1/llm/execute \
  -H "Authorization: Bearer $USER_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "코드 변경사항을 인덱스에 반영하고 블로그 글도 써줘",
    "context": {
      "diff": {
        "files": [{"path": "src/main.py", "status": "modified"}]
      }
    }
  }'
```

### 3. Python 클라이언트

```python
import httpx

API_URL = "http://localhost:8000"

async def post_article(user_jwt: str, title: str, markdown: str):
    """블로그 글 발행"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/v1/commands/execute",
            headers={"Authorization": f"Bearer {user_jwt}"},
            json={
                "name": "post_blog_article",
                "params": {
                    "title": title,
                    "markdown": markdown
                }
            }
        )
        return response.json()

async def apply_diff(user_jwt: str, files: list):
    """코드 diff 적용 (사용자별로 격리됨)"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/v1/diffs/apply",
            headers={"Authorization": f"Bearer {user_jwt}"},
            json={"files": files}
        )
        return response.json()

async def execute_natural_language_command(
    user_jwt: str, 
    prompt: str, 
    context: dict = None
):
    """자연어 명령을 LLM에게 전달하여 실행"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/v1/llm/execute",
            headers={"Authorization": f"Bearer {user_jwt}"},
            json={
                "prompt": prompt,
                "context": context or {},
                "model": "claude-3-5-sonnet"
            }
        )
        return response.json()

# 사용 예시
async def main():
    # 사용자 JWT (TS ↔ Java Auth 서버에서 발급받아 저장)
    user_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."
    
    # Diff 적용
    result = await apply_diff(user_jwt, [
        {
            "path": "src/main.py",
            "status": "modified",
            "after": "print('hello')"
        }
    ])
    print(result)
```

## 🔒 데이터 격리

각 사용자의 데이터는 완전히 격리되어 다른 사용자가 접근할 수 없습니다.

### Vector DB (Qdrant)
```python
# 포인트 ID: md5(user_id + file_path)
file_id = hashlib.md5(f"{user_id}:{file_path}".encode()).hexdigest()

# Payload에 user_id 포함
{
  "user_id": 1,
  "file": "src/main.py",
  "content_preview": "print('hello')",
  ...
}

# 조회 시 user_id로 필터링
filter = Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))])
```

### Graph DB (Neo4j)
```cypher
-- 모든 노드에 user_id 속성
MERGE (f:File {path: $path, user_id: $user_id})
MERGE (e:Entity {name: $name, file: $file, user_id: $user_id})
MERGE (m:Module {name: $module, user_id: $user_id})

-- 조회 시 user_id로 필터링
MATCH (f:File {user_id: $user_id})
RETURN f
```

### WAL (Write-Ahead Log)
```json
{
  "id": "1234567890_123456",
  "timestamp": "2024-11-02T12:00:00",
  "user_id": 1,
  "operation": "upsert",
  "file": "src/main.py",
  "status": "success"
}
```

### 데이터 격리 테스트

```bash
# User 1: 파일 업로드
curl -X POST -H "Authorization: Bearer user1_jwt" \
     -d '{"files":[{"path":"test.py","status":"modified","after":"print(1)"}]}' \
     http://localhost:8000/api/v1/diffs/apply

# User 2: 같은 경로에 다른 파일 업로드
curl -X POST -H "Authorization: Bearer user2_jwt" \
     -d '{"files":[{"path":"test.py","status":"modified","after":"print(2)"}]}' \
     http://localhost:8000/api/v1/diffs/apply

# → 두 사용자의 데이터는 완전히 분리됨
```

## MCP 서버 실행

stdio 기반 JSON-RPC MCP 서버를 실행하려면:

```bash
python -m src.mcp.server
```

MCP 클라이언트가 stdin/stdout으로 JSON-RPC 메시지를 교환할 수 있습니다.

## 사용 가능한 툴

1. **post_blog_article** - 블로그 글 발행 (RAG를 통한 정확도 향상)
2. **search_vector_db** - Vector DB 기반 의미 검색
3. **search_graph_db** - Graph DB 기반 구조/호출 관계 검색

> **참고**: 코드 인덱스 업데이트는 클라이언트(VSCode Extension)가 `/api/v1/diffs/apply`를 통해 자동으로 처리합니다.

## 백그라운드 작업

### 자동 실행 스케줄

| 작업 | 주기 | 설명 |
|-----|-----|-----|
| `wal_recovery_task` | 5분 | 실패한 WAL 작업 재시도 (content 복원하여) |
| `wal_cleanup_task` | 1일 | 7일 이상 된 성공 WAL 엔트리 정리 |

⚠️ **주의**: 서버는 사용자 로컬 파일에 접근할 수 없습니다. 전체 스캔/재인덱싱은 **클라이언트(VSCode extension)가 주도**합니다.

### WAL (Write-Ahead Log) 상세

#### 파일 구조
```
data/
├─ wal.jsonl              # 메타데이터 로그
└─ wal_content/
   ├─ 1730000000_123.txt  # 실제 파일 내용
   └─ 1730000001_456.txt
```

#### 메타데이터 예시 (data/wal.jsonl)
```jsonl
{"id": "1730000000_123", "timestamp": "2024-11-02T12:00:00", "operation": "upsert", "file": "src/main.py", "hash": "abc123", "content_file": "wal_content/1730000000_123.txt", "content_length": 1024, "status": "pending"}
{"id": "1730000001_456", "timestamp": "2024-11-02T12:00:01", "operation": "delete", "file": "src/old.py", "hash": null, "content_file": null, "content_length": 0, "status": "success", "completed_at": "2024-11-02T12:00:02"}
```

#### 상태 설명
- **pending**: 작업 대기 중
- **success**: 작업 완료 (7일 후 자동 삭제)
- **failed**: 작업 실패 (5분마다 자동 재시도)

#### 복구 메커니즘
1. DB 업데이트 실패 시 WAL에 `failed` 표시
2. 5분마다 `wal_recovery_task`가 실패한 작업 조회
3. WAL에서 content 복원 (`data/wal_content/{id}.txt`)
4. Vector DB (임베딩 생성) + Graph DB (코드 파싱) 재시도
5. 성공 시 `success` 표시, 실패 시 다시 `failed`

### 작동 흐름

#### 실시간 증분 업데이트
```
[VSCode Extension]        [Python Server]             [Databases]
      │                         │                         │
파일 변경 감지                  │                         │
      │                         │                         │
      ├─ POST /diffs/apply ──→  │                         │
      │  (before/after)          │                         │
      │                          │                         │
      │                      1. WAL 기록                   │
      │                      data/wal.jsonl               │
      │                      data/wal_content/*.txt       │
      │                          │                         │
      │                      2. Vector DB ──────────────→ Qdrant
      │                      (OpenAI embedding)           (upsert)
      │                          │                         │
      │                      3. Graph DB ───────────────→ Neo4j
      │                      (AST parsing)              (nodes/rels)
      │                          │                         │
      │                      4. WAL 상태 업데이트          │
      │                      (success/failed)             │
      │                          │                         │
      │  ← 200 OK (통계) ────────┤                         │
```

#### 백그라운드 복구 프로세스
```
[5분마다: WAL Recovery]
1. 실패한 작업 조회 (status="failed")
2. data/wal_content/{id}.txt에서 content 복원
3. Vector DB + Graph DB 재시도
4. 성공 → "success", 실패 → 계속 "failed"

[1일마다: WAL Cleanup]
1. 7일 이상 된 "success" 엔트리 조회
2. data/wal.jsonl에서 제거
3. data/wal_content/{id}.txt 파일 삭제
```

#### 클라이언트(VSCode Extension) 역할
```
[30분마다 or 수동]
1. 로컬에서 전체 파일 스캔
2. POST /diffs/apply (전체 파일 전송)
3. 서버는 이를 증분 업데이트로 처리
   → 기존 파일 해시 비교
   → 변경/신규/삭제 파일 자동 감지
```

## 아키텍처 설계 원칙

### 클라이언트-서버 분리
- ✅ **클라이언트**: 파일 시스템 접근, 전체 스캔, 주기적 동기화
- ✅ **서버**: 증분 업데이트 처리, DB 관리, 실패 복구
- ❌ **불가능**: 서버가 사용자 로컬 파일 시스템 스캔

### WAL 설계 이점
1. **내구성**: 모든 업데이트가 디스크에 먼저 기록됨
2. **복구 가능**: 실패한 작업을 자동으로 재시도
3. **감사 추적**: 모든 변경사항의 완전한 로그
4. **효율성**: Content를 별도 파일로 저장하여 메타데이터 검색 빠름

## 🔧 문제 해결

### "Invalid or expired token" 에러
- 사용자 JWT가 만료되었는지 확인 (`exp` 클레임)
- TS ↔ Java Auth 서버에서 새 JWT를 발급받아 전송
- Python 로그(`get_current_user`)에서 상세 에러 확인

### 서비스 토큰 오류
- Java → Python 호출 시 서비스 JWT 사용 여부 확인
- `JAVA_BACKEND_SERVICE_JWT_*` 환경 변수가 올바른지 검증
- 필요 시 `refresh_service_jwt()`로 재발급

### 데이터가 격리되지 않음
- 모든 DB 작업에 `user_id`가 전달되는지 로그 확인
- Vector DB 포인트에 `user_id` 필드 존재 여부 확인
- Graph DB 노드에 `user_id` 속성 존재 여부 확인

## 📊 개발자 도구

### 사용자 DB 확인
```bash
sqlite3 data/users.db
sqlite> SELECT id, github_id, username, email FROM users;
```

### WAL 확인
```bash
# WAL 통계
curl http://localhost:8000/api/v1/admin/wal-stats

# 수동 WAL 복구
curl -X POST http://localhost:8000/api/v1/admin/wal-recovery
```

### Vector DB 확인 (Qdrant)
```bash
# 특정 사용자의 포인트 조회
curl http://localhost:6333/collections/code_embeddings/points/scroll \
  -d '{"filter": {"must": [{"key": "user_id", "match": {"value": 1}}]}}'
```

### Graph DB 확인 (Neo4j)
```cypher
// Neo4j Browser에서 실행
MATCH (f:File {user_id: 1})
RETURN f.path, f.updated_at
LIMIT 10;
```

## ✅ 구현 완료 항목

- [x] WAL 구현 (content 별도 파일 저장)
- [x] 백그라운드 스케줄러 (WAL 복구, 정리)
- [x] Vector DB 실제 구현 (Qdrant + OpenAI)
- [x] Graph DB 실제 구현 (Neo4j + AST 파싱)
- [x] 클라이언트-서버 아키텍처 분리
- [x] **다중 사용자 지원** ✨
  - [x] GitHub OAuth 2.0 인증
  - [x] 사용자별 API 키 자동 생성
  - [x] Vector DB 데이터 격리 (`user_id` 필터링)
  - [x] Graph DB 데이터 격리 (`user_id` 속성)
  - [x] WAL 사용자 추적 (`user_id` 로그)
  - [x] 모든 라우터 다중 사용자 지원

## 🚧 향후 계획

- [ ] TypeScript 클라이언트(VSCode Extension) 연결
- [ ] 실제 블로그 API 연동 (현재 더미 구현)
- [ ] 성능 최적화 및 모니터링
- [ ] 프로덕션 배포 가이드
- [ ] 사용자 관리 대시보드
- [ ] API 사용량 통계

## 의존성

주요 라이브러리:
- `fastapi` - REST API 프레임워크
- `uvicorn` - ASGI 서버
- `pydantic` - 데이터 검증
- `httpx` - HTTP 클라이언트 (GitHub OAuth용)
- `openai` - OpenAI API 클라이언트 (GPT, 임베딩)
- `qdrant-client` - Qdrant Vector DB 클라이언트
- `neo4j` - Neo4j Graph DB 드라이버
- `APScheduler` - 백그라운드 작업 스케줄러
- `pytest` - 테스트 프레임워크
- `sqlite3` - 사용자 DB (Python 내장)

## 라이선스

MIT

## 📚 참고 자료

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Neo4j Documentation](https://neo4j.com/docs/)
- [GitHub OAuth Documentation](https://docs.github.com/en/developers/apps/building-oauth-apps)

## 📝 추가 문서

자세한 설정 가이드는 다음 문서를 참고하세요:
- **다중 사용자 설정**: 상세한 GitHub OAuth 설정 및 데이터 격리 확인 방법
- **구현 세부사항**: 아키텍처 변경사항 및 기술적 세부사항

---

**Made with ❤️ for developers who love clean architecture and multi-user support**

