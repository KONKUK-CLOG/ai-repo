# TS-LLM-MCP Bridge

FastAPI + MCP 서버 프로젝트. TypeScript 클라이언트가 보낸 코드 증분(diff)과 LLM 명령을 Python 서버가 처리하며, 동일 기능을 MCP(Model Context Protocol) 툴로도 노출합니다.

## 특징

- **REST API Only**: SSE/WebSocket 없이 순수 REST로 구현
- **API Key 인증**: 모든 엔드포인트는 `x-api-key` 헤더로 인증
- **Idempotency 지원**: `x-idempotency-key` 헤더로 중복 방지
- **MCP 툴 노출**: LLM이 안전하게 호출할 수 있는 MCP 프로토콜 지원
- **어댑터 패턴**: 외부 서비스(블로그, Vector DB, Graph DB, Notion, GitHub)를 어댑터로 분리

## 프로젝트 구조

```
ts-llm-mcp-bridge/
├─ src/
│  ├─ server/              # FastAPI 서버
│  │  ├─ main.py          # 앱 엔트리 포인트
│  │  ├─ settings.py      # 환경 설정
│  │  ├─ deps.py          # 의존성 주입
│  │  ├─ schemas.py       # Pydantic 스키마
│  │  └─ routers/         # API 라우터
│  │     ├─ health.py     # 헬스체크
│  │     ├─ diffs.py      # Diff 적용
│  │     └─ commands.py   # 명령 실행
│  ├─ adapters/           # 외부 서비스 어댑터
│  │  ├─ blog_api.py      # 블로그 API
│  │  ├─ vector_db.py     # Vector DB
│  │  ├─ graph_db.py      # Graph DB
│  │  ├─ notion.py        # Notion
│  │  └─ github.py        # GitHub
│  └─ mcp/                # MCP 서버 및 툴
│     ├─ server.py        # stdio JSON-RPC 서버
│     └─ tools/           # MCP 툴들
│        ├─ post_blog_article.py
│        ├─ update_code_index.py
│        ├─ refresh_rag_indexes.py
│        ├─ publish_to_notion.py
│        └─ create_commit_and_push.py
├─ tests/                 # 테스트
├─ requirements.txt       # Python 의존성
├─ Dockerfile            # Docker 이미지
└─ README.md
```

## API 엔드포인트

### 헬스체크

- `GET /healthz` - 기본 헬스체크
- `GET /readyz` - 준비 상태 체크

### Diff 적용

- `POST /api/v1/diffs/apply` - 코드 증분을 벡터/그래프 인덱스에 증분 반영

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

### 명령 실행

- `GET /api/v1/commands` - 사용 가능한 명령(툴) 스키마 조회
- `POST /api/v1/commands/execute` - 고수준 명령(툴) 실행

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
```

### Python 클라이언트

```python
import httpx

API_URL = "http://localhost:8000"
API_KEY = "dev-api-key"

async def post_article(title: str, markdown: str):
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

## 라이선스

MIT

## 참고

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Pydantic Documentation](https://docs.pydantic.dev/)

