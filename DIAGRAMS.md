# Clog System Architecture Diagrams

This document contains Mermaid diagrams visualizing the architecture and workflows of the Clog system (TS-LLM-MCP Bridge).

## LLM Agent Flow - Class Diagram

The following class diagram illustrates the LLM agent flow from Java server request to blog draft generation:

```mermaid
classDiagram
    %% External Systems
    class JavaServer {
        +POST /internal/v1/llm/execute
        +receive_llm_response()
        +GET /api/v1/blog/posts
    }

    %% FastAPI Router Layer
    class AgentRouter {
        +execute_llm_command(request: LLMExecuteRequest)
        +call_llm_with_tools(prompt, context, tools, model)
        +_execute_regular_tool(tool_name, params)
        +_generate_final_response(prompt, tool_calls, model)
        +_fallback_tool_selection(prompt, context)
    }

    %% LLM Service
    class LLMService {
        +AsyncOpenAI client
        +system_prompt: str
        +analyze_request(prompt, context, tools)
        +decide_tool_usage()
        +generate_response()
    }

    %% Tool Registry
    class TOOLS_REGISTRY {
        +get_user_blog_posts: GetUserBlogPostsTool
        +get_available_tools()
    }

    %% MCP Tool
    class GetUserBlogPostsTool {
        +TOOL: dict
        +run(params: Dict) Dict
        +validate_params(params)
    }

    %% Adapter Layer
    class BlogAPIAdapter {
        +get_user_articles(user_id, limit, offset) Dict
    }

    class JavaBackendAdapter {
        +get_user_blog_posts(user_id, limit, offset) Dict
        +_request(method, path, json_body, headers) Dict
    }

    %% Data Models
    class LLMExecuteRequest {
        +user_id: int
        +prompt: str
        +context: Dict[str, Any]
        +model: Optional[str]
        +max_iterations: int
    }

    class LLMExecuteResult {
        +ok: bool
        +thought: Optional[str]
        +tool_calls: List[ToolCall]
        +final_response: str
        +model_used: Optional[str]
    }

    class ToolCall {
        +tool: str
        +params: Dict[str, Any]
        +result: Any
        +success: bool
    }

    class Settings {
        +OPENAI_API_KEY: str
        +DEFAULT_LLM_MODEL: str
        +LLM_TEMPERATURE: float
        +LLM_MAX_TOKENS: int
    }

    %% Relationships
    JavaServer --> AgentRouter
    AgentRouter --> LLMExecuteRequest
    AgentRouter --> LLMService
    AgentRouter --> TOOLS_REGISTRY
    AgentRouter --> LLMExecuteResult
    LLMExecuteResult --> JavaServer

    LLMService --> Settings
    LLMService --> TOOLS_REGISTRY
    LLMService ..> AgentRouter

    TOOLS_REGISTRY --> GetUserBlogPostsTool
    AgentRouter --> GetUserBlogPostsTool
    GetUserBlogPostsTool --> BlogAPIAdapter
    BlogAPIAdapter --> JavaBackendAdapter
    JavaBackendAdapter --> JavaServer

    AgentRouter --> ToolCall
    LLMExecuteResult --> ToolCall

    %% Styling with CSS classes
    classDef javaServer fill:#e74c3c,stroke:#c0392b,stroke-width:3px,color:#fff
    classDef agentRouter fill:#3498db,stroke:#2980b9,stroke-width:3px,color:#fff
    classDef llmService fill:#9b59b6,stroke:#8e44ad,stroke-width:3px,color:#fff
    classDef toolRegistry fill:#f39c12,stroke:#e67e22,stroke-width:3px,color:#fff
    classDef blogTool fill:#1abc9c,stroke:#16a085,stroke-width:3px,color:#fff
    classDef blogAdapter fill:#27ae60,stroke:#229954,stroke-width:3px,color:#fff
    classDef javaAdapter fill:#e67e22,stroke:#d35400,stroke-width:3px,color:#fff
    classDef dataModel fill:#95a5a6,stroke:#7f8c8d,stroke-width:3px,color:#fff
    classDef settings fill:#34495e,stroke:#2c3e50,stroke-width:3px,color:#fff

```

## LLM Agent Flow - Sequence Diagram

The following sequence diagram shows the detailed flow of LLM request processing:

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'noteTextColor':'#000', 'noteBkgColor':'#fff', 'noteBorderColor':'#000', 'actorTextColor':'#000', 'actorLineColor':'#000', 'signalColor':'#000', 'signalTextColor':'#000', 'labelBoxBkgColor':'#fff', 'labelBoxBorderColor':'#000', 'labelTextColor':'#000', 'loopTextColor':'#000', 'activationBorderColor':'#000', 'activationBkgColor':'#f0f0f0', 'sequenceNumberColor':'#000'}}}%%
sequenceDiagram
    participant JavaServer as Java Server
    participant AgentRouter as AgentRouter<br/>(Python)
    participant LLMService as LLM Service<br/>(OpenAI)
    participant ToolRegistry as TOOLS_REGISTRY
    participant BlogTool as GetUserBlogPostsTool
    participant BlogAPI as BlogAPIAdapter
    participant JavaBackend as JavaBackendAdapter

    %% Request Flow
    rect rgb(200, 220, 250)
        Note over JavaServer,JavaBackend: LLM Request Processing Flow
        JavaServer->>AgentRouter: POST /internal/v1/llm/execute<br/>{user_id, prompt, context}
        AgentRouter->>ToolRegistry: Get available tools
        ToolRegistry-->>AgentRouter: [get_user_blog_posts]
        
        AgentRouter->>LLMService: call_llm_with_tools(prompt, context, tools)
        Note over LLMService: System Prompt:<br/>"블로그 글 참고 필요 시<br/>get_user_blog_posts 호출"
        LLMService->>LLMService: Analyze request<br/>(블로그 기록 참고 필요?)
        
        alt 블로그 기록 참고 필요
            LLMService-->>AgentRouter: tool_calls: [get_user_blog_posts]
            AgentRouter->>AgentRouter: Auto-inject user_id<br/>from request
            AgentRouter->>BlogTool: run({user_id, limit, offset})
            BlogTool->>BlogAPI: get_user_articles(user_id, limit, offset)
            BlogAPI->>JavaBackend: get_user_blog_posts(user_id, limit, offset)
            JavaBackend->>JavaServer: GET /api/v1/blog/posts<br/>?user_id={user_id}&limit={limit}&offset={offset}
            JavaServer-->>JavaBackend: {posts: [...], total, limit, offset}
            JavaBackend-->>BlogAPI: Blog posts result
            BlogAPI-->>BlogTool: {posts: [...], total, limit, offset}
            BlogTool-->>AgentRouter: Tool execution result<br/>(user's blog history)
            AgentRouter->>LLMService: _generate_final_response(prompt, tool_calls)
            Note over LLMService: LLM analyzes user's<br/>blog style and generates<br/>markdown draft
            LLMService-->>AgentRouter: Final response<br/>(markdown blog draft)
        else 블로그 기록 참고 불필요
            LLMService-->>AgentRouter: tool_calls: []<br/>(no tools)
            Note over AgentRouter: LLM이 직접 답변 생성
            AgentRouter->>LLMService: _generate_final_response(prompt, [])
            LLMService-->>AgentRouter: Direct response text
        end
        
        AgentRouter->>AgentRouter: Create LLMExecuteResult<br/>{ok, thought, tool_calls, final_response}
        AgentRouter-->>JavaServer: HTTP 200<br/>LLMExecuteResult<br/>(markdown draft, not published)
        Note over JavaServer: 사용자가 마크다운 초안을<br/>확인/수정 후 Java 서버로<br/>직접 게시 요청
    end
```

### Class Details (구현 기반 상세 설명)

- **JavaServer**  
  - LLM 호출을 트리거하는 상위 시스템입니다. `POST /internal/v1/llm/execute` 요청에 `user_id`, `prompt`, `context`를 담아 Python 서버로 전달하고, 작업 완료 후 `LLMExecuteResult`를 받아 사용자에게 전달합니다.  
  - Python 서버가 블로그 히스토리를 조회할 때에도 Java 서버가 제공하는 `GET /api/v1/blog/posts` 엔드포인트가 사용되므로, 입력-출력 모두에 관여합니다. (`src/server/routers/agent.py`, `src/adapters/java_backend.py`)

- **AgentRouter**  
  - FastAPI 라우터 계층으로, LLM 요청 라이프사이클 전체를 관리합니다.  
  - 주요 책임:  
    1. `TOOLS_REGISTRY`에서 사용 가능한 MCP 툴들을 수집  
    2. `call_llm_with_tools`로 OpenAI API를 호출하여 시스템 프롬프트와 툴 목록을 전달  
    3. LLM이 선택한 툴을 `_execute_regular_tool`로 실행하면서 `user_id` 같은 필수 파라미터를 자동 주입  
    4. 툴 결과를 합쳐 `_generate_final_response`로 최종 마크다운 초안을 생성  
  - 장애 상황에서는 `_fallback_tool_selection`과 `_create_fallback_response`로 안전하게 응답합니다. (`src/server/routers/agent.py`)

- **LLMService**  
  - `call_llm_with_tools`와 `_generate_final_response` 함수로 구현된 가상 서비스 계층입니다.  
  - `AsyncOpenAI` 클라이언트를 생성해 시스템 프롬프트, 사용자 메시지, 툴 스키마를 전달하고, 모델이 반환한 `tool_calls`를 파싱해 에이전트에게 알려줍니다.  
  - 최종 응답 생성 시에는 각 툴 결과를 요약하여 LLM에 다시 전달, 사용자 친화적인 2~3문장 마크다운 답변을 받아 돌려줍니다. (`src/server/routers/agent.py`)

- **TOOLS_REGISTRY**  
  - 에이전트에서 사용할 수 있는 모든 MCP 툴을 중앙에서 관리하는 딕셔너리입니다.  
  - 현재 활성화된 항목은 `get_user_blog_posts` 하나지만, 향후 Vector/Graph DB 툴을 주석 해제하면 즉시 확장할 수 있도록 구조화되어 있습니다.  
  - LLM에 전달할 스키마(`tool.TOOL`) 조회와 실제 실행 모듈(`tool.run`) 참조를 동시에 맡습니다. (`src/server/routers/agent.py`)

- **GetUserBlogPostsTool**  
  - MCP 표준 형식에 맞춘 메타데이터(`name`, `description`, `input_schema`)와 실행 함수(`run`)를 제공합니다.  
  - `user_id` 필수 확인 후 `limit`, `offset` 기본값을 적용하고 `blog_api.get_user_articles`로 실제 데이터를 가져옵니다.  
  - 반환 값은 포스트 리스트와 전체 개수, 페이지 정보가 포함되어 LLM이 스타일/태그 패턴을 분석하는 데 사용됩니다. (`src/mcp/tools/get_user_blog_posts.py`)

- **BlogAPIAdapter**  
  - Python 서버 내부에서 Java 백엔드 호출을 캡슐화하는 얇은 추상화 계층입니다.  
  1. `java_backend.get_user_blog_posts` 호출  
  2. 응답 포스트 수를 로깅해 관측성을 확보  
  3. 실패 시 `httpx.HTTPError`를 그대로 던져 상위 라우터가 적절히 처리할 수 있도록 합니다. (`src/adapters/blog_api.py`)

- **JavaBackendAdapter**  
  - Java 서버와의 모든 HTTP 통신 규칙을 담당합니다.  
  - `_build_url`, `_build_headers`, `_request` 유틸 함수를 통해 베이스 URL/타임아웃/로깅/에러 처리를 표준화하며, `get_user_blog_posts` 같은 도메인 함수는 이를 재사용합니다.  
  - 현재는 같은 EC2 내 통신을 가정하여 JWT 헤더 없이 호출하고, 응답 JSON 디코딩 실패 시 명확한 예외를 던집니다. (`src/adapters/java_backend.py`)

- **LLMExecuteRequest**  
  - Java 서버→Python 서버 호출 시 바디를 검증하는 Pydantic 모델입니다.  
  - 사용자의 자연어 명령(`prompt`) 외에도 자유형 컨텍스트(`context`), 특정 모델 강제(`model`), 무한루프 방지용 반복 제한(`max_iterations`)을 명시적으로 선언합니다. (`src/server/schemas.py`)

- **LLMExecuteResult**  
  - 에이전트 실행 결과를 Java 서버에 전달하는 표준 응답입니다.  
  - `ok` 상태, LLM 사고 과정(`thought`), 각 툴 실행 기록(`tool_calls`), 사용자에게 보여줄 최종 마크다운(`final_response`), 실제 사용 모델(`model_used`)을 포함합니다.  
  - Java 서버는 이 구조를 그대로 프론트엔드/사용자에게 전달하거나 추가 로깅에 활용할 수 있습니다. (`src/server/schemas.py`)

- **ToolCall**  
  - 개별 툴 실행 단위를 표현하는 모델로, 어떤 툴이 어떤 파라미터와 함께 호출됐고 성공했는지 여부, 결과 페이로드를 보존합니다.  
  - AgentRouter의 실행 루프와 `LLMExecuteResult.tool_calls`에 동일한 구조를 사용해 디버깅과 회귀 분석이 용이합니다. (`src/server/schemas.py`)

- **Settings**  
  - `pydantic_settings.BaseSettings`를 상속해 `.env` 기반 환경 설정을 로드합니다.  
  - 서버 바인딩 정보, Java 백엔드 URL/타임아웃, OpenAI API 키와 기본 모델, Vector/Graph DB 설정, 기능 플래그 등을 한 곳에서 관리하며 `settings = Settings()` 싱글턴으로 전역 접근을 제공합니다. (`src/server/settings.py`)

## Component Descriptions

### AgentRouter
- **execute_llm_command**: Main endpoint that receives LLM execution requests from Java server
- **call_llm_with_tools**: Calls OpenAI API with system prompt and available tools
- **_execute_regular_tool**: Executes a tool from the registry
- **_generate_final_response**: Generates user-friendly final response using LLM
- **Auto-inject user_id**: Automatically injects `user_id` from request into `get_user_blog_posts` tool calls

### LLMService
- **System Prompt**: Instructs LLM to analyze requests and call `get_user_blog_posts` when user's blog history should be referenced
- **Tool Selection**: LLM decides whether to use `get_user_blog_posts` tool based on whether blog history reference is needed
- **Response Generation**: Creates final response (markdown blog draft) based on tool execution results and user's blog style

### GetUserBlogPostsTool
- **TOOL**: Tool metadata (name, description, input_schema)
- **run**: Retrieves user's blog post history with user_id, limit, and offset parameters
- Returns blog posts with metadata (title, content, tags, created_at, etc.)

### BlogAPIAdapter
- **get_user_articles**: Retrieves user's blog articles via Java backend
- Handles error cases and logging
- Returns blog posts list with pagination metadata

### JavaBackendAdapter
- **get_user_blog_posts**: Sends HTTP GET request to Java server blog API
- Endpoint: `GET /api/v1/blog/posts?user_id={user_id}&limit={limit}&offset={offset}`
- Internal communication (no JWT required)

## Decision Flow

1. **Java Server** sends LLM request with `user_id`, `prompt`, and `context`
2. **AgentRouter** receives request and gets available tools from registry
3. **LLMService** analyzes the request using system prompt:
   - If user's blog history should be referenced (blog writing request, style matching needed, etc.): Selects `get_user_blog_posts` tool
   - If not needed (simple question unrelated to blog): Responds directly without tools
4. **If tool selected**: 
   - AgentRouter auto-injects `user_id` from request
   - Tool executes → BlogAPIAdapter → JavaBackendAdapter → Java Server (GET request)
   - Returns user's blog post history
5. **Final response**: LLM analyzes user's blog style and generates markdown blog draft (not published)
6. **User action**: User reviews/edits the draft and publishes directly to Java server (Python server not involved in publishing)

---

## Next Semester: Diff Application & WAL Processing - Sequence Diagram

**⚠️ 다음 학기 구현 예정**: 현재 주석 처리된 코드를 기반으로 한 예상 흐름입니다.

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'noteTextColor':'#000', 'noteBkgColor':'#fff', 'noteBorderColor':'#000', 'actorTextColor':'#000', 'actorLineColor':'#000', 'signalColor':'#000', 'signalTextColor':'#000', 'labelBoxBkgColor':'#fff', 'labelBoxBorderColor':'#000', 'labelTextColor':'#000', 'loopTextColor':'#000', 'activationBorderColor':'#000', 'activationBkgColor':'#f0f0f0', 'sequenceNumberColor':'#000'}}}%%
sequenceDiagram
    participant JavaServer as Java Server
    participant DiffsRouter as DiffsRouter<br/>(Python)
    participant WAL as WriteAheadLog
    participant VectorDB as VectorDBAdapter
    participant GraphDB as GraphDBAdapter
    participant OpenAI as OpenAI<br/>(Embeddings)
    participant Qdrant as Qdrant<br/>(Vector DB)
    participant Neo4j as Neo4j<br/>(Graph DB)
    participant Scheduler as BackgroundScheduler

    %% Diff Application Flow
    rect rgb(220, 250, 220)
        Note over JavaServer,Neo4j: Diff Application with WAL (다음 학기 구현 예정)
        JavaServer->>DiffsRouter: POST /internal/v1/diffs/apply<br/>{user_id, files: [{path, status, before, after}]}
        
        DiffsRouter->>DiffsRouter: Validate input<br/>(unified or files)
        
        loop For each file change
            DiffsRouter->>WAL: append({type: "upsert", file, content, hash, user_id})
            WAL->>WAL: Save content to<br/>data/wal_content/{id}.txt
            WAL->>WAL: Log metadata to<br/>data/wal.jsonl<br/>(status: "pending")
            WAL-->>DiffsRouter: wal_id
        end
        
        DiffsRouter->>VectorDB: upsert_embeddings(documents, user_id)
        loop For each document
            VectorDB->>OpenAI: Generate embedding<br/>(text-embedding-3-small)
            OpenAI-->>VectorDB: embedding vector
            VectorDB->>Qdrant: upsert({id, vector, payload})
            Qdrant-->>VectorDB: Success
        end
        VectorDB-->>DiffsRouter: embeddings_upserted count
        
        DiffsRouter->>GraphDB: update_code_graph(files, contents, user_id)
        loop For each file
            GraphDB->>GraphDB: Parse AST<br/>(Python: ast module)
            GraphDB->>GraphDB: Extract entities<br/>(functions, classes, imports)
            GraphDB->>Neo4j: Create/update nodes<br/>(File, Function, Class)
            GraphDB->>Neo4j: Create relationships<br/>(CALLS, IMPORTS, CONTAINS)
            Neo4j-->>GraphDB: Success
        end
        GraphDB-->>DiffsRouter: graph_nodes_updated count
        
        loop For each successful file
            DiffsRouter->>WAL: mark_success(wal_id)
            WAL->>WAL: Update status to "success"<br/>in data/wal.jsonl
        end
        
        DiffsRouter-->>JavaServer: DiffApplyResult<br/>{files_processed, embeddings_upserted, graph_nodes_updated}
    end

    %% Background Recovery Flow
    rect rgb(250, 220, 220)
        Note over Scheduler,Neo4j: WAL Recovery (5분마다 실행, 다음 학기 구현 예정)
        Scheduler->>WAL: get_failed_operations()
        WAL-->>Scheduler: List of failed entries<br/>(status: "failed")
        
        loop For each failed operation
            Scheduler->>WAL: get_content(entry_id)
            WAL->>WAL: Read from<br/>data/wal_content/{id}.txt
            WAL-->>Scheduler: File content
            
            alt Operation type: upsert
                Scheduler->>VectorDB: upsert_embeddings([{file, content}])
                VectorDB->>OpenAI: Generate embedding
                OpenAI-->>VectorDB: embedding vector
                VectorDB->>Qdrant: upsert
                Qdrant-->>VectorDB: Success
                VectorDB-->>Scheduler: Success
                
                Scheduler->>GraphDB: update_code_graph([file], {file: content})
                GraphDB->>GraphDB: Parse AST
                GraphDB->>Neo4j: Create/update nodes & relationships
                Neo4j-->>GraphDB: Success
                GraphDB-->>Scheduler: Success
                
                Scheduler->>WAL: mark_success(entry_id)
            else Operation type: delete
                Scheduler->>VectorDB: delete_embeddings([file_path])
                VectorDB->>Qdrant: delete points
                Qdrant-->>VectorDB: Success
                
                Scheduler->>GraphDB: delete_file_nodes([file_path])
                GraphDB->>Neo4j: Delete nodes & relationships
                Neo4j-->>GraphDB: Success
                
                Scheduler->>WAL: mark_success(entry_id)
            end
        end
    end

    %% WAL Cleanup Flow
    rect rgb(250, 230, 200)
        Note over Scheduler,WAL: WAL Cleanup (1일마다 실행, 다음 학기 구현 예정)
        Scheduler->>WAL: cleanup_old_entries(days=7)
        WAL->>WAL: Find entries with<br/>status="success" and<br/>completed_at > 7 days
        loop For each old entry
            WAL->>WAL: Delete from<br/>data/wal.jsonl
            WAL->>WAL: Delete file<br/>data/wal_content/{id}.txt
        end
        WAL-->>Scheduler: Cleanup completed
    end
```

### Diff Application & WAL Processing - Component Descriptions

#### DiffsRouter
- **apply_diff**: Receives diff requests from Java server and processes file changes
- **Input validation**: Validates unified diff or files array format
- **WAL logging**: Logs all operations to WAL before execution
- **Error handling**: Marks operations as success/failure in WAL

#### WriteAheadLog (WAL)
- **append**: Logs operation metadata to `data/wal.jsonl` and saves content to `data/wal_content/{id}.txt`
- **mark_success/mark_failure**: Updates operation status in WAL
- **get_failed_operations**: Retrieves failed operations for recovery
- **get_content**: Restores file content from WAL content files
- **cleanup_old_entries**: Removes old successful entries (7+ days)

#### VectorDBAdapter
- **upsert_embeddings**: Generates embeddings using OpenAI and upserts to Qdrant
- **delete_embeddings**: Deletes embeddings from Qdrant
- **semantic_search**: Performs semantic search (used by RAG tools)

#### GraphDBAdapter
- **update_code_graph**: Parses code AST and creates/updates nodes and relationships in Neo4j
- **delete_file_nodes**: Deletes file-related nodes from Neo4j
- **search_related_code**: Searches code entities and relationships (used by RAG tools)

#### BackgroundScheduler
- **wal_recovery_task**: Runs every 5 minutes to retry failed WAL operations
- **wal_cleanup_task**: Runs daily to clean up old WAL entries

---

## Next Semester: RAG (Retrieval-Augmented Generation) - Sequence Diagram

**⚠️ 다음 학기 구현 예정**: 현재 주석 처리된 RAG 툴을 기반으로 한 예상 흐름입니다.

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'noteTextColor':'#000', 'noteBkgColor':'#fff', 'noteBorderColor':'#000', 'actorTextColor':'#000', 'actorLineColor':'#000', 'signalColor':'#000', 'signalTextColor':'#000', 'labelBoxBkgColor':'#fff', 'labelBoxBorderColor':'#000', 'labelTextColor':'#000', 'loopTextColor':'#000', 'activationBorderColor':'#000', 'activationBkgColor':'#f0f0f0', 'sequenceNumberColor':'#000'}}}%%
sequenceDiagram
    participant JavaServer as Java Server
    participant AgentRouter as AgentRouter<br/>(Python)
    participant LLMService as LLM Service<br/>(OpenAI)
    participant ToolRegistry as TOOLS_REGISTRY
    participant VectorTool as SearchVectorDBTool
    participant GraphTool as SearchGraphDBTool
    participant VectorDB as VectorDBAdapter
    participant GraphDB as GraphDBAdapter
    participant OpenAI as OpenAI<br/>(Embeddings)
    participant Qdrant as Qdrant<br/>(Vector DB)
    participant Neo4j as Neo4j<br/>(Graph DB)

    %% RAG Flow with Vector DB
    rect rgb(200, 250, 250)
        Note over JavaServer,Neo4j: RAG: Vector DB Semantic Search (다음 학기 구현 예정)
        JavaServer->>AgentRouter: POST /internal/v1/llm/execute<br/>{user_id, prompt: "사용자 인증 로직 찾아줘"}
        AgentRouter->>ToolRegistry: Get available tools
        ToolRegistry-->>AgentRouter: [get_user_blog_posts,<br/>search_vector_db,<br/>search_graph_db]
        
        AgentRouter->>LLMService: call_llm_with_tools(prompt, context, tools)
        Note over LLMService: System Prompt:<br/>"RAG 도구로 관련 코드 검색 후<br/>블로그 글 작성"
        LLMService->>LLMService: Analyze request<br/>(코드 검색 필요)
        LLMService-->>AgentRouter: tool_calls: [search_vector_db]
        
        AgentRouter->>VectorTool: run({query: "사용자 인증", top_k: 10, user_id})
        VectorTool->>VectorDB: semantic_search(query, user_id, top_k)
        VectorDB->>OpenAI: Generate query embedding<br/>(text-embedding-3-small)
        OpenAI-->>VectorDB: query_embedding vector
        VectorDB->>Qdrant: search(collection, query_vector, top_k, filter: user_id)
        Qdrant-->>VectorDB: Results with scores<br/>[{file, content_preview, score}]
        VectorDB-->>VectorTool: Search results
        VectorTool-->>AgentRouter: {success: true, results: [...]}
        
        AgentRouter->>LLMService: _generate_final_response(prompt, tool_calls)
        Note over LLMService: LLM uses search results<br/>as context for response
        LLMService-->>AgentRouter: Final response with<br/>code references
        AgentRouter-->>JavaServer: LLMExecuteResult<br/>{tool_calls, final_response}
    end

    %% RAG Flow with Graph DB
    rect rgb(250, 200, 250)
        Note over JavaServer,Neo4j: RAG: Graph DB Structure Search (다음 학기 구현 예정)
        JavaServer->>AgentRouter: POST /internal/v1/llm/execute<br/>{user_id, prompt: "authenticate 함수가<br/>어떤 함수를 호출하는지 알려줘"}
        AgentRouter->>LLMService: call_llm_with_tools(prompt, context, tools)
        LLMService->>LLMService: Analyze request<br/>(함수 호출 관계 검색 필요)
        LLMService-->>AgentRouter: tool_calls: [search_graph_db]
        
        AgentRouter->>GraphTool: run({query: "authenticate", limit: 10, user_id})
        GraphTool->>GraphDB: search_related_code(query, user_id, limit)
        GraphDB->>Neo4j: MATCH (f:Function)<br/>WHERE f.name CONTAINS "authenticate"<br/>AND f.user_id = {user_id}<br/>OPTIONAL MATCH (f)-[r:CALLS]->(called)<br/>RETURN f, r, called
        Neo4j-->>GraphDB: Entities with relationships<br/>[{entity_name, entity_type, calls: [...]}]
        GraphDB-->>GraphTool: Search results
        GraphTool-->>AgentRouter: {success: true, results: [...]}
        
        AgentRouter->>LLMService: _generate_final_response(prompt, tool_calls)
        LLMService-->>AgentRouter: Final response with<br/>function call relationships
        AgentRouter-->>JavaServer: LLMExecuteResult
    end

    %% Combined RAG Flow
    rect rgb(250, 250, 200)
        Note over JavaServer,Neo4j: RAG: Combined Vector + Graph Search (다음 학기 구현 예정)
        JavaServer->>AgentRouter: POST /internal/v1/llm/execute<br/>{user_id, prompt: "사용자 인증 관련 코드를<br/>찾아서 블로그 글 작성해줘"}
        AgentRouter->>LLMService: call_llm_with_tools(prompt, context, tools)
        LLMService->>LLMService: Analyze request<br/>(코드 검색 + 블로그 작성)
        LLMService-->>AgentRouter: tool_calls: [search_vector_db,<br/>search_graph_db,<br/>get_user_blog_posts]
        
        par Vector DB Search
            AgentRouter->>VectorTool: run({query: "사용자 인증", user_id})
            VectorTool->>VectorDB: semantic_search(...)
            VectorDB->>Qdrant: search(...)
            Qdrant-->>VectorDB: Results
            VectorDB-->>VectorTool: Results
            VectorTool-->>AgentRouter: Vector search results
        and Graph DB Search
            AgentRouter->>GraphTool: run({query: "authenticate", user_id})
            GraphTool->>GraphDB: search_related_code(...)
            GraphDB->>Neo4j: MATCH ... RETURN ...
            Neo4j-->>GraphDB: Results
            GraphDB-->>GraphTool: Results
            GraphTool-->>AgentRouter: Graph search results
        and Blog History Retrieval
            AgentRouter->>BlogTool: run({user_id, limit, offset})
            BlogTool->>BlogAPI: get_user_articles(...)
            BlogAPI->>JavaBackend: get_user_blog_posts(...)
            JavaBackend->>JavaServer: GET /api/v1/blog/posts
            JavaServer-->>JavaBackend: User's blog posts
            JavaBackend-->>BlogAPI: Blog history
            BlogAPI-->>BlogTool: Blog posts
            BlogTool-->>AgentRouter: User's blog history
        end
        
        AgentRouter->>LLMService: _generate_final_response(prompt, tool_calls)
        Note over LLMService: LLM combines Vector + Graph<br/>results + user's blog style<br/>as context
        LLMService-->>AgentRouter: Markdown blog draft<br/>(not published)
        
        AgentRouter-->>JavaServer: LLMExecuteResult<br/>{tool_calls, final_response:<br/>markdown draft}
        Note over JavaServer: User reviews/edits draft<br/>and publishes directly
    end
```

### RAG - Component Descriptions

#### SearchVectorDBTool
- **TOOL**: Tool metadata for semantic search
- **run**: Executes semantic search using embeddings
- **Parameters**: `query` (search text), `top_k` (number of results), `user_id` (auto-injected)

#### SearchGraphDBTool
- **TOOL**: Tool metadata for graph-based code structure search
- **run**: Executes graph search for code entities and relationships
- **Parameters**: `query` (entity name), `limit` (max results), `user_id` (auto-injected)

#### VectorDBAdapter (RAG usage)
- **semantic_search**: Generates query embedding and searches Qdrant for similar code
- **Returns**: File paths, content previews, similarity scores
- **User isolation**: Filters results by `user_id`

#### GraphDBAdapter (RAG usage)
- **search_related_code**: Searches Neo4j for code entities matching query
- **Returns**: Entity information (functions, classes) with call relationships
- **User isolation**: Filters results by `user_id`

### RAG Decision Flow

1. **LLM analyzes request**: Determines if code search is needed
2. **Tool selection**:
   - **search_vector_db**: When semantic similarity search is needed (e.g., "사용자 인증 로직 찾아줘")
   - **search_graph_db**: When code structure/relationships are needed (e.g., "authenticate 함수가 호출하는 함수들")
   - **Both tools**: When comprehensive code context is needed
3. **Search execution**: Tools query Vector DB and/or Graph DB
4. **Context injection**: Search results are passed to LLM as context
5. **Response generation**: LLM generates response using code context
