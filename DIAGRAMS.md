# Clog System Architecture Diagrams

This document contains Mermaid diagrams visualizing the architecture and workflows of the Clog system (TS-LLM-MCP Bridge).

## LLM Agent Flow - Class Diagram

The following class diagram illustrates the LLM agent flow from Java server request to blog publishing:

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'mainBkg':'#e8f4f8', 'secondBkg':'#f0f0f0', 'mainContrastColor':'#000', 'darkMode':'false', 'background':'#ffffff', 'tertiaryBorderColor':'#000', 'tertiaryTextColor':'#000', 'fontSize':'16px', 'nodeBorder':'#2c3e50', 'clusterBkg':'#ecf0f1', 'clusterBorder':'#34495e', 'titleColor':'#000', 'edgeLabelBackground':'#fff', 'classText':'#000'}}}%%
classDiagram
    %% External Systems
    class JavaServer {
        +POST /internal/v1/llm/execute
        +receive_llm_response()
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
        +post_blog_article: PostBlogArticleTool
        +get_available_tools()
    }

    %% MCP Tool
    class PostBlogArticleTool {
        +TOOL: dict
        +run(params: Dict) Dict
        +validate_params(params)
    }

    %% Adapter Layer
    class BlogAPIAdapter {
        +publish_article(title, markdown, tags, api_key) Dict
    }

    class JavaBackendAdapter {
        +create_blog_post(api_key, payload) Dict
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
        +BLOG_API_KEY: str
        +DEFAULT_LLM_MODEL: str
        +LLM_TEMPERATURE: float
        +LLM_MAX_TOKENS: int
    }

    %% Relationships
    JavaServer --> AgentRouter : POST /internal/v1/llm/execute
    AgentRouter --> LLMExecuteRequest : receives
    AgentRouter --> LLMService : uses
    AgentRouter --> TOOLS_REGISTRY : queries
    AgentRouter --> LLMExecuteResult : returns
    LLMExecuteResult --> JavaServer : HTTP response

    LLMService --> Settings : reads OPENAI_API_KEY
    LLMService --> TOOLS_REGISTRY : gets available tools
    LLMService ..> AgentRouter : returns tool_calls

    TOOLS_REGISTRY --> PostBlogArticleTool : contains
    AgentRouter --> PostBlogArticleTool : executes
    PostBlogArticleTool --> BlogAPIAdapter : calls
    PostBlogArticleTool --> Settings : reads BLOG_API_KEY
    BlogAPIAdapter --> JavaBackendAdapter : uses
    JavaBackendAdapter --> JavaServer : HTTP POST /api/v1/blog/posts

    AgentRouter --> ToolCall : creates
    LLMExecuteResult --> ToolCall : contains

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

    class JavaServer javaServer
    class AgentRouter agentRouter
    class LLMService llmService
    class TOOLS_REGISTRY toolRegistry
    class PostBlogArticleTool blogTool
    class BlogAPIAdapter blogAdapter
    class JavaBackendAdapter javaAdapter
    class LLMExecuteRequest,LLMExecuteResult,ToolCall dataModel
    class Settings settings
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
    participant BlogTool as PostBlogArticleTool
    participant BlogAPI as BlogAPIAdapter
    participant JavaBackend as JavaBackendAdapter

    %% Request Flow
    rect rgb(200, 220, 250)
        Note over JavaServer,JavaBackend: LLM Request Processing Flow
        JavaServer->>AgentRouter: POST /internal/v1/llm/execute<br/>{user_id, prompt, context}
        AgentRouter->>ToolRegistry: Get available tools
        ToolRegistry-->>AgentRouter: [post_blog_article]
        
        AgentRouter->>LLMService: call_llm_with_tools(prompt, context, tools)
        Note over LLMService: System Prompt:<br/>"요청을 분석하여<br/>블로그 게시 필요 여부 판단"
        LLMService->>LLMService: Analyze request<br/>(블로그 게시 필요?)
        
        alt 블로그 게시 필요
            LLMService-->>AgentRouter: tool_calls: [post_blog_article]
            AgentRouter->>BlogTool: run({title, markdown, tags})
            BlogTool->>BlogAPI: publish_article(title, markdown, tags, api_key)
            BlogAPI->>JavaBackend: create_blog_post(api_key, payload)
            JavaBackend->>JavaServer: POST /api/v1/blog/posts<br/>(X-User-Api-Key header)
            JavaServer-->>JavaBackend: {article_id, url, ...}
            JavaBackend-->>BlogAPI: Blog post result
            BlogAPI-->>BlogTool: {success: true, article: {...}}
            BlogTool-->>AgentRouter: Tool execution result
            AgentRouter->>LLMService: _generate_final_response(prompt, tool_calls)
            LLMService-->>AgentRouter: Final response text
        else 블로그 게시 불필요
            LLMService-->>AgentRouter: tool_calls: []<br/>(no tools)
            Note over AgentRouter: LLM이 직접 답변 생성
            AgentRouter->>LLMService: _generate_final_response(prompt, [])
            LLMService-->>AgentRouter: Direct response text
        end
        
        AgentRouter->>AgentRouter: Create LLMExecuteResult<br/>{ok, thought, tool_calls, final_response}
        AgentRouter-->>JavaServer: HTTP 200<br/>LLMExecuteResult
    end
```

## Component Descriptions

### AgentRouter
- **execute_llm_command**: Main endpoint that receives LLM execution requests from Java server
- **call_llm_with_tools**: Calls OpenAI API with system prompt and available tools
- **_execute_regular_tool**: Executes a tool from the registry
- **_generate_final_response**: Generates user-friendly final response using LLM

### LLMService
- **System Prompt**: Instructs LLM to analyze requests and decide if blog publishing is needed
- **Tool Selection**: LLM decides whether to use `post_blog_article` tool or respond directly
- **Response Generation**: Creates final response based on tool execution results

### PostBlogArticleTool
- **TOOL**: Tool metadata (name, description, input_schema)
- **run**: Executes blog publishing with title, markdown, and tags
- Uses `settings.BLOG_API_KEY` from Python server .env

### BlogAPIAdapter
- **publish_article**: Publishes article via Java backend
- Validates API key and formats payload

### JavaBackendAdapter
- **create_blog_post**: Sends HTTP POST request to Java server blog API
- Uses `X-User-Api-Key` header for authentication

## Decision Flow

1. **Java Server** sends LLM request with `user_id`, `prompt`, and `context`
2. **AgentRouter** receives request and gets available tools from registry
3. **LLMService** analyzes the request using system prompt:
   - If blog publishing is needed (explicit request like "블로그에 올려줘"): Selects `post_blog_article` tool
   - If not needed (simple question): Responds directly without tools
4. **If tool selected**: Tool executes → BlogAPIAdapter → JavaBackendAdapter → Java Server
5. **Final response**: LLM generates user-friendly response and returns to Java Server

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
        ToolRegistry-->>AgentRouter: [post_blog_article,<br/>search_vector_db,<br/>search_graph_db]
        
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
        LLMService-->>AgentRouter: tool_calls: [search_vector_db,<br/>search_graph_db,<br/>post_blog_article]
        
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
        end
        
        AgentRouter->>LLMService: _generate_final_response(prompt, tool_calls)
        Note over LLMService: LLM combines Vector + Graph<br/>results as context
        LLMService-->>AgentRouter: Response with code context
        
        AgentRouter->>AgentRouter: Execute post_blog_article<br/>with code context
        AgentRouter-->>JavaServer: LLMExecuteResult<br/>{tool_calls, final_response}
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
