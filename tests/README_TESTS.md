# Test Suite Documentation

## Overview

Comprehensive unit tests with mocking for all major features. Tests are independent of external APIs (OpenAI, Qdrant, Neo4j, GitHub) and use dummy data.

## Test Files

### 1. `test_auth.py` - GitHub OAuth Authentication
Tests for GitHub OAuth login, callback, user creation, and API key authentication.

```bash
pytest tests/test_auth.py -v
```

**Tests:**
- GitHub login redirect
- OAuth callback success
- New user creation
- API key authentication
- Invalid API key handling
- User data isolation

### 2. `test_vector_db.py` - Vector DB Operations
Tests for Qdrant vector database operations with semantic search.

```bash
pytest tests/test_vector_db.py -v
```

**Tests:**
- Semantic search functionality
- User ID filtering
- Embedding upsert
- File deletion
- User data isolation
- Empty result handling

### 3. `test_graph_db.py` - Graph DB Operations
Tests for Neo4j graph database operations with code relationships.

```bash
pytest tests/test_graph_db.py -v
```

**Tests:**
- Related code search
- Relationship tracking (function calls)
- Code graph updates
- Python file parsing
- User ID filtering
- Connection failure handling

### 4. `test_agent_rag.py` - RAG Integration
Tests for RAG-enhanced blog writing with Vector + Graph DB.

```bash
pytest tests/test_agent_rag.py -v
```

**Tests:**
- Blog article generation with RAG
- top_k allocation (70% vector, 30% graph)
- File deduplication between DBs
- RAG context formatting
- Empty results handling
- User isolation in RAG

### 5. `test_diffs_apply.py` - Diff Application
Tests for applying code diffs to databases.

```bash
pytest tests/test_diffs_apply.py -v
```

**Tests:**
- Unified diff mode
- Files array mode
- API key validation
- Invalid input handling

### 6. `test_agent_execute.py` - LLM Agent
Tests for LLM agent command execution.

```bash
pytest tests/test_agent_execute.py -v
```

**Tests:**
- Blog request handling
- Multiple task execution
- Custom model support
- Thought process generation

## Running Tests

### All Tests
```bash
# Run all tests with verbose output
pytest tests/ -v

# Run all tests with coverage report
pytest tests/ -v --cov=src

# Run all tests with detailed coverage
pytest tests/ -v --cov=src --cov-report=html
```

### Specific Test File
```bash
pytest tests/test_auth.py -v
pytest tests/test_vector_db.py -v
pytest tests/test_graph_db.py -v
pytest tests/test_agent_rag.py -v
```

### Specific Test Function
```bash
pytest tests/test_auth.py::test_github_login_redirect -v
pytest tests/test_vector_db.py::test_semantic_search -v
```

### With Print Statements
```bash
pytest tests/ -v -s
```

### Stop on First Failure
```bash
pytest tests/ -v -x
```

### Run Only Failed Tests
```bash
pytest tests/ -v --lf
```

## Mock Fixtures

All tests use the following mock fixtures from `conftest.py`:

- `mock_user` - Dummy user (id=1, username="testuser")
- `mock_user_repo` - Mock user repository
- `mock_openai_embeddings` - Mock OpenAI embeddings API
- `mock_openai_chat` - Mock OpenAI chat API
- `mock_qdrant_client` - Mock Qdrant vector DB
- `mock_neo4j_driver` - Mock Neo4j graph DB
- `mock_github_api` - Mock GitHub OAuth API

## Dummy Data

### User
```python
{
    "id": 1,
    "github_id": 12345678,
    "username": "testuser",
    "email": "testuser@example.com",
    "api_key": "test-key-123"
}
```

### Vector DB Results
```python
[
    {
        "file": "src/test.py",
        "content": "def test(): pass",
        "score": 0.85,
        "user_id": 1
    }
]
```

### Graph DB Results
```python
[
    {
        "entity_name": "test_function",
        "entity_type": "function",
        "file": "src/test.py",
        "line_start": 10,
        "line_end": 20,
        "calls": ["helper_func"]
    }
]
```

## Environment Setup

Tests run independently of your `.env` file. All external APIs are mocked.

**No need to set:**
- OPENAI_API_KEY
- GITHUB_CLIENT_ID
- GITHUB_CLIENT_SECRET
- VECTOR_DB_URL
- GRAPH_DB_URL

## CI/CD Integration

Tests are designed to run in CI/CD environments without external dependencies:

```yaml
# GitHub Actions example
- name: Run tests
  run: |
    pytest tests/ -v --cov=src
```

## Test Coverage

Run coverage report:
```bash
# Terminal report
pytest tests/ --cov=src --cov-report=term

# HTML report (opens in browser)
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

## Troubleshooting

### Import Errors
```bash
# Make sure you're in the project root
cd /path/to/Clog

# Install in editable mode
pip install -e .
```

### Fixture Not Found
```bash
# Make sure conftest.py is in tests/ directory
ls tests/conftest.py
```

### Async Tests Failing
```bash
# Install pytest-asyncio
pip install pytest-asyncio
```

## Benefits

✅ **Fast**: No external API calls  
✅ **Reliable**: Predictable mock data  
✅ **Isolated**: Tests don't interfere with each other  
✅ **Complete**: Coverage for all major features  
✅ **CI-Ready**: No configuration required  

## Next Steps

1. Run all tests: `pytest tests/ -v`
2. Check coverage: `pytest tests/ --cov=src`
3. Fix any failures
4. Add more tests as needed

