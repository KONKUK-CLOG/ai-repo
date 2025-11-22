# Clog System Architecture Diagrams

This document contains Mermaid diagrams visualizing the architecture and workflows of the Clog system (TS-LLM-MCP Bridge).

## LLM Agent Flow - Class Diagram

The following class diagram illustrates the LLM agent flow from Java server request to blog publishing:

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'mainBkg':'#fff', 'secondBkg':'#f0f0f0', 'mainContrastColor':'#000', 'darkMode':'false', 'background':'#fff', 'tertiaryBorderColor':'#000', 'tertiaryTextColor':'#000', 'fontSize':'16px', 'nodeBorder':'#000', 'clusterBkg':'#f0f0f0', 'clusterBorder':'#000', 'titleColor':'#000', 'edgeLabelBackground':'#fff', 'classText':'#000'}}}%%
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

## Sequence Diagram

The following sequence diagram illustrates the main workflows in the system:

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'noteTextColor':'#000', 'noteBkgColor':'#fff', 'noteBorderColor':'#000', 'actorTextColor':'#000', 'actorLineColor':'#000', 'signalColor':'#000', 'signalTextColor':'#000', 'labelBoxBkgColor':'#fff', 'labelBoxBorderColor':'#000', 'labelTextColor':'#000', 'loopTextColor':'#000', 'activationBorderColor':'#000', 'activationBkgColor':'#f0f0f0', 'sequenceNumberColor':'#000'}}}%%
sequenceDiagram
    participant User
    participant Browser
    participant FastAPI as FastAPI Server
    participant GitHub
    participant UserRepo as User Repository
    participant Client as VSCode Extension
    participant WAL as Write-Ahead Log
    participant VectorDB as Vector DB (Qdrant)
    participant GraphDB as Graph DB (Neo4j)
    participant Claude as Claude Desktop
    participant MCP as MCP Server
    participant Scheduler as Background Scheduler

    %% GitHub OAuth Authentication Flow
    rect rgb(200, 220, 250)
        Note over User,UserRepo: GitHub OAuth Authentication
        User->>Browser: Click login
        Browser->>FastAPI: GET /auth/github/login
        FastAPI->>GitHub: Redirect to OAuth
        GitHub->>User: Request authorization
        User->>GitHub: Approve
        GitHub->>FastAPI: GET /auth/github/callback?code=...
        FastAPI->>GitHub: Exchange code for access token
        GitHub-->>FastAPI: Access token + user info
        FastAPI->>UserRepo: Create/update user
        UserRepo-->>FastAPI: User with API key
        FastAPI-->>Browser: Return API key + user info
    end

    %% Diff Application with WAL Flow
    rect rgb(220, 250, 220)
        Note over Client,GraphDB: Diff Application with WAL
        Client->>FastAPI: POST /api/v1/diffs/apply<br/>(x-api-key, files diff)
        FastAPI->>UserRepo: Validate API key
        UserRepo-->>FastAPI: User validated
        FastAPI->>WAL: Log operation (pending)
        WAL-->>FastAPI: Entry created
        FastAPI->>VectorDB: Generate embeddings & upsert
        VectorDB-->>FastAPI: Success
        FastAPI->>GraphDB: Parse AST & create nodes/relationships
        GraphDB-->>FastAPI: Success
        FastAPI->>WAL: Update status (success)
        FastAPI-->>Client: Return statistics
    end

    %% MCP Tool Execution Flow
    rect rgb(250, 230, 200)
        Note over Claude,MCP: MCP Tool Execution
        Claude->>MCP: JSON-RPC: initialize
        MCP-->>Claude: Server capabilities
        Claude->>MCP: JSON-RPC: tools/list
        MCP-->>Claude: Available tools list
        Claude->>MCP: JSON-RPC: tools/call<br/>(name, arguments)
        MCP->>MCP: Execute tool function
        MCP-->>Claude: Tool result
    end

    %% Background Recovery Flow
    rect rgb(250, 220, 220)
        Note over Scheduler,WAL: Background Recovery (Every 5 min)
        Scheduler->>WAL: Check for failed operations
        WAL-->>Scheduler: List of failed entries
        loop For each failed entry
            Scheduler->>WAL: Read content from file
            Scheduler->>VectorDB: Retry upsert
            Scheduler->>GraphDB: Retry update
            Scheduler->>WAL: Update status
        end
    end
```

### Workflow Descriptions

1. **GitHub OAuth Authentication**: Users authenticate via GitHub OAuth to receive a unique API key. The system creates or updates user records and ensures data isolation per user.

2. **Diff Application with WAL**: VSCode extension sends code changes to the server. All updates are logged to WAL first (Write-Ahead Log), then processed by Vector DB for semantic search and Graph DB for code relationships. Failed operations are automatically retried.

3. **MCP Tool Execution**: Claude Desktop communicates with the MCP Server via JSON-RPC over stdio. Tools include blog posting plus Vector/Graph database searches.

4. **Background Recovery**: A scheduler runs every 5 minutes to retry failed WAL operations, ensuring data consistency and reliability.

## Class Diagram

The following class diagram shows the main components and their relationships:

```mermaid
%%{init: {'theme':'base', 'themeVariables': { 'primaryColor':'#fff', 'primaryTextColor':'#000', 'primaryBorderColor':'#000', 'lineColor':'#000', 'secondaryColor':'#f0f0f0', 'tertiaryColor':'#fff', 'mainBkg':'#fff', 'secondBkg':'#f0f0f0', 'mainContrastColor':'#000', 'darkMode':'false', 'background':'#fff', 'tertiaryBorderColor':'#000', 'tertiaryTextColor':'#000', 'fontSize':'16px', 'nodeBorder':'#000', 'clusterBkg':'#f0f0f0', 'clusterBorder':'#000', 'titleColor':'#000', 'edgeLabelBackground':'#fff', 'classText':'#000'}}}%%
classDiagram
    %% FastAPI Server Components
    class FastAPIApp {
        +CORSMiddleware
        +lifespan()
        +include_router()
    }

    class AuthRouter {
        +github_login()
        +github_callback()
        +github_logout()
    }

    class DiffsRouter {
        +apply_diffs()
        +validate_api_key()
    }

    class AgentRouter {
        +execute_llm_command()
        +natural_language_processing()
    }

    class CommandsRouter {
        +list_commands()
        +execute_command()
    }

    class HealthRouter {
        +healthz()
        +readyz()
    }

    %% MCP Server Components
    class MCPServer {
        -bool initialized
        +handle_request()
        +initialize()
        +list_tools()
        +call_tool()
        +run()
    }

    class ToolRegistry {
        +TOOLS[]
        +TOOL_EXECUTORS{}
    }

    class PostBlogTool {
        +TOOL
        +run(arguments)
    }

    class SearchVectorTool {
        +TOOL
        +run(arguments)
    }

    class SearchGraphTool {
        +TOOL
        +run(arguments)
    }

    %% Adapter Components
    class VectorDBAdapter {
        +get_qdrant_client()
        +generate_embedding()
        +upsert_file()
        +delete_file()
        +search()
    }

    class GraphDBAdapter {
        +get_neo4j_driver()
        +parse_python_file()
        +upsert_file()
        +delete_file()
        +search()
    }

    class BlogAPIAdapter {
        +post_article()
        +update_article()
    }

    class GitHubAdapter {
        +oauth_exchange()
        +get_user_info()
        +create_commit()
    }

    %% Background Components
    class BackgroundScheduler {
        
        +start_scheduler()
        +shutdown_scheduler()
        +run_task_now()
    }

    class WAL {
        +log_operation()
        +update_status()
        +get_failed_entries()
        +cleanup_old_entries()
        +get_statistics()
    }

    class Tasks {
        +wal_recovery_task()
        +wal_cleanup_task()
    }

    %% Data Layer
    class User {
        +int id
        +int github_id
        +str username
        +str email
        +str api_key
        +datetime created_at
    }

    class UserRepository {
        +create_user()
        +get_user_by_api_key()
        +get_user_by_github_id()
        +update_user()
    }

    %% Relationships
    FastAPIApp --> AuthRouter
    FastAPIApp --> DiffsRouter
    FastAPIApp --> AgentRouter
    FastAPIApp --> CommandsRouter
    FastAPIApp --> HealthRouter
    FastAPIApp --> BackgroundScheduler

    AuthRouter --> GitHubAdapter
    AuthRouter --> UserRepository

    DiffsRouter --> UserRepository
    DiffsRouter --> WAL
    DiffsRouter --> VectorDBAdapter
    DiffsRouter --> GraphDBAdapter

    AgentRouter --> UserRepository
    AgentRouter --> ToolRegistry

    CommandsRouter --> UserRepository
    CommandsRouter --> ToolRegistry

    MCPServer --> ToolRegistry
    ToolRegistry --> PostBlogTool
    ToolRegistry --> SearchVectorTool
    ToolRegistry --> SearchGraphTool

    PostBlogTool --> BlogAPIAdapter
    SearchVectorTool --> VectorDBAdapter
    SearchGraphTool --> GraphDBAdapter

    BackgroundScheduler --> Tasks
    Tasks --> WAL
    Tasks --> VectorDBAdapter
    Tasks --> GraphDBAdapter

    UserRepository --> User

    VectorDBAdapter ..> User : filters by user_id
    GraphDBAdapter ..> User : filters by user_id
    WAL ..> User : tracks user_id
```

### Component Descriptions

#### FastAPI Server
- **FastAPIApp**: Main application with CORS middleware and router management
- **Routers**: Handle different API endpoints (auth, diffs, agent, commands, health)
- All routers use user authentication and data isolation by `user_id`

#### MCP Server
- **MCPServer**: Stdio-based JSON-RPC 2.0 server for LLM integration
- **ToolRegistry**: Central registry of available tools and their executors
- **Tools**: Individual tool implementations for blog posting plus Vector/Graph DB searches

#### Adapters
- **VectorDBAdapter**: Qdrant client for semantic search with OpenAI embeddings
- **GraphDBAdapter**: Neo4j client for code relationship tracking with AST parsing
- **BlogAPIAdapter**: Blog posting functionality
- **GitHubAdapter**: GitHub OAuth integration

#### Background Processing
- **BackgroundScheduler**: APScheduler for periodic tasks
- **WAL**: Write-Ahead Log for operation durability and recovery
- **Tasks**: Scheduled tasks for WAL recovery (5 min) and cleanup (1 day)

#### Data Layer
- **User**: User model with GitHub OAuth info and API key
- **UserRepository**: SQLite-based user data access layer
- All data operations are filtered by `user_id` for multi-user isolation

## Architecture Principles

1. **Multi-User Support**: Complete data isolation using `user_id` filtering in all databases
2. **Durability**: WAL ensures all operations are logged before execution
3. **Fault Tolerance**: Background scheduler automatically retries failed operations
4. **Clean Architecture**: Adapter pattern separates external service integrations
5. **Dual Interface**: REST API for clients + MCP for LLM integration
