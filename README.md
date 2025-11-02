# TS-LLM-MCP Bridge

FastAPI + MCP 서버 프로젝트. TypeScript 클라이언트가 보낸 코드 증분(diff)과 LLM 명령을 Python 서버가 처리하며, 동일 기능을 MCP(Model Context Protocol) 툴로도 노출합니다.

## 특징

- **REST API Only**: SSE/WebSocket 없이 순수 REST로 구현
- **API Key 인증**: 모든 엔드포인트는 `x-api-key` 헤더로 인증
- **Idempotency 지원**: `x-idempotency-key` 헤더로 중복 방지
- **MCP 툴 노출**: LLM이 안전하게 호출할 수 있는 MCP 프로토콜 지원
- **어댑터 패턴**: 외부 서비스(블로그, Vector DB, Graph DB, Notion, GitHub)를 어댑터로 분리
- **WAL (Write-Ahead Log)**: 모든 업데이트를 로그에 먼저 기록, 실패 시 자동 복구 (content 별도 파일 저장)
- **백그라운드 스케줄러**: 5분마다 WAL 복구, 1일마다 WAL 정리 (클라이언트 주도 동기화)
- **Vector DB 통합**: Qdrant를 사용한 시맨틱 검색 (OpenAI 임베딩)
- **Graph DB 통합**: Neo4j를 사용한 코드 관계 추적 (함수 호출, 임포트 등)

## 프로젝트 구조

```
ts-llm-mcp-bridge/
├─ src/
│  ├─ server/              # FastAPI 서버
│  │  ├─ main.py          # 앱 엔트리 포인트 + 백그라운드 스케줄러
│  │  ├─ settings.py      # 환경 설정
│  │  ├─ deps.py          # 의존성 주입
│  │  ├─ schemas.py       # Pydantic 스키마
│  │  └─ routers/         # API 라우터
│  │     ├─ health.py     # 헬스체크
│  │     ├─ diffs.py      # Diff 적용 (WAL 통합)
│  │     ├─ agent.py      # LLM 에이전트 (OpenAI GPT)
│  │     └─ commands.py   # 명령 실행 (개발 전용)
│  ├─ adapters/           # 외부 서비스 어댑터 (실제 구현)
│  │  ├─ blog_api.py      # 블로그 API
│  │  ├─ vector_db.py     # Qdrant Vector DB
│  │  ├─ graph_db.py      # Neo4j Graph DB
│  │  ├─ notion.py        # Notion
│  │  └─ github.py        # GitHub
│  ├─ background/         # 백그라운드 작업
│  │  ├─ wal.py          # Write-Ahead Log (content 별도 파일 저장)
│  │  ├─ scheduler.py    # APScheduler
│  │  └─ tasks.py        # 주기적 작업 (WAL 복구, WAL 정리)
│  └─ mcp/                # MCP 서버 및 툴
│     ├─ server.py        # stdio JSON-RPC 서버
│     └─ tools/           # MCP 툴들
│        ├─ post_blog_article.py
│        ├─ update_code_index.py
│        ├─ refresh_rag_indexes.py
│        ├─ publish_to_notion.py
│        └─ create_commit_and_push.py
├─ data/                  # WAL 로그 (git ignored)
│  ├─ wal.jsonl          # WAL 메타데이터
│  └─ wal_content/       # WAL content 파일들
├─ tests/                 # 테스트
├─ requirements.txt       # Python 의존성
├─ Dockerfile            # Docker 이미지
└─ README.md
```

## API 엔드포인트

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
SERVER_API_KEY=your-server-api-key-here
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Blog API
BLOG_API_URL=https://api.example.com/blog
BLOG_API_KEY=your-blog-api-key

# Vector Database
VECTOR_DB_URL=http://localhost:6333
VECTOR_DB_COLLECTION=code_embeddings
EMBED_BATCH_SIZE=100

# Graph Database
GRAPH_DB_URL=bolt://localhost:7687
GRAPH_DB_USER=neo4j
GRAPH_DB_PASSWORD=your-graph-db-password

# Notion
NOTION_TOKEN=your-notion-token

# GitHub
GITHUB_TOKEN=your-github-token

# LLM API
OPENAI_API_KEY=your-openai-api-key
DEFAULT_LLM_MODEL=gpt-4-turbo-preview
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.7

# Feature Flags
ENABLE_DIRECT_TOOLS=false  # true: 개발 환경에서만 활성화

# Limits
MAX_DIFF_BYTES=10485760
```

## 설치 및 실행

### 로컬 개발

1. **의존성 설치**:
```bash
pip install -r requirements.txt
```

2. **환경 변수 설정**:
```bash
cp .env.example .env
# .env 파일을 편집하여 실제 값 입력
```

**중요: LLM 에이전트 사용을 위해서는 OpenAI API 키가 필요합니다**
```env
OPENAI_API_KEY=sk-...your-actual-key...
```
- [OpenAI API Keys](https://platform.openai.com/api-keys)에서 키 발급
- API 키가 없으면 키워드 기반 폴백 모드로 동작

**개발 환경에서만 직접 툴 실행 엔드포인트 활성화하기**
```env
ENABLE_DIRECT_TOOLS=true  # 개발 시 툴 직접 테스트
```
- ⚠️ 프로덕션에서는 `false`로 설정 (기본값)
- `true`로 설정 시 `/api/v1/commands/*` 엔드포인트 활성화

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

### cURL로 API 호출

```bash
# 헬스체크
curl http://localhost:8000/healthz

# 명령 목록 조회
curl -H "x-api-key: dev-api-key" http://localhost:8000/api/v1/commands

# 블로그 포스트 발행
curl -X POST http://localhost:8000/api/v1/commands/execute \
  -H "x-api-key: dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "post_blog_article",
    "params": {
      "title": "Test Article",
      "markdown": "# Hello World"
    }
  }'

# Diff 적용
curl -X POST http://localhost:8000/api/v1/diffs/apply \
  -H "x-api-key: dev-api-key" \
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

# LLM 에이전트로 자연어 명령 실행
curl -X POST http://localhost:8000/api/v1/llm/execute \
  -H "x-api-key: dev-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "코드 변경사항을 인덱스에 반영하고 블로그 글도 써줘",
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
  }'
```

### Python 클라이언트

```python
import httpx

API_URL = "http://localhost:8000"
API_KEY = "dev-api-key"

async def post_article(title: str, markdown: str):
    """직접 툴을 지정하여 실행"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/v1/commands/execute",
            headers={"x-api-key": API_KEY},
            json={
                "name": "post_blog_article",
                "params": {
                    "title": title,
                    "markdown": markdown
                }
            }
        )
        return response.json()

async def execute_natural_language_command(prompt: str, context: dict = None):
    """자연어 명령을 LLM에게 전달하여 실행"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/api/v1/llm/execute",
            headers={"x-api-key": API_KEY},
            json={
                "prompt": prompt,
                "context": context or {},
                "model": "claude-3-5-sonnet"
            }
        )
        return response.json()

# 사용 예시
# result = await execute_natural_language_command(
#     "이 코드 변경사항을 인덱스에 추가하고 블로그에도 올려줘",
#     context={"diff": {...}}
# )
```

## MCP 서버 실행

stdio 기반 JSON-RPC MCP 서버를 실행하려면:

```bash
python -m src.mcp.server
```

MCP 클라이언트가 stdin/stdout으로 JSON-RPC 메시지를 교환할 수 있습니다.

## 사용 가능한 툴

1. **post_blog_article** - 블로그 글 발행
2. **update_code_index** - 코드 인덱스 증분 업데이트
3. **refresh_rag_indexes** - RAG 인덱스 전역 리프레시
4. **publish_to_notion** - Notion 페이지 발행
5. **create_commit_and_push** - Git 커밋 & 푸시

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

## 의존성

주요 라이브러리:
- `fastapi` - REST API 프레임워크
- `uvicorn` - ASGI 서버
- `pydantic` - 데이터 검증
- `httpx` - HTTP 클라이언트
- `openai` - OpenAI API 클라이언트 (GPT, 임베딩)
- `qdrant-client` - Qdrant Vector DB 클라이언트
- `neo4j` - Neo4j Graph DB 드라이버
- `APScheduler` - 백그라운드 작업 스케줄러
- `pytest` - 테스트 프레임워크

## 라이선스

MIT

## 참고

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Neo4j Documentation](https://neo4j.com/docs/)

