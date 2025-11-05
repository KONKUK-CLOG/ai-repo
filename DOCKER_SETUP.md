# Docker Setup Guide

## Quick Start

### 1. Build Docker Image
```bash
make build
# Or without make:
docker-compose build
```

### 2. Run Tests
```bash
make test
# Or without make:
docker-compose run --rm test
```

### 3. Start Server
```bash
make up
# Or without make:
docker-compose up -d app
```

## Available Commands

### Using Makefile (Recommended)

```bash
# Build Docker image
make build

# Start server
make up

# Stop server
make down

# Run tests
make test

# Run tests with coverage report
make test-coverage

# Open shell in container
make shell

# View logs
make logs

# Restart services
make restart

# Clean up everything
make clean

# Start with all services (including DBs)
make up-full

# Development mode with live reload
make dev
```

### Using Docker Compose Directly

```bash
# Build
docker-compose build

# Run tests
docker-compose run --rm test

# Run specific test file
docker-compose run --rm test pytest tests/test_auth.py -v

# Run with coverage
docker-compose run --rm test pytest tests/ -v --cov=src --cov-report=html

# Start server
docker-compose up -d app

# View logs
docker-compose logs -f app

# Stop all services
docker-compose down

# Clean up volumes
docker-compose down -v
```

## Running Tests

### All Tests
```bash
make test
```

### Specific Test File
```bash
docker-compose run --rm test pytest tests/test_auth.py -v
```

### With Coverage Report
```bash
make test-coverage
# Opens htmlcov/index.html in browser
```

### Watch Mode (re-run on failures)
```bash
make test-watch
```

### With Print Statements
```bash
docker-compose run --rm test pytest tests/ -v -s
```

## Development Workflow

### 1. Initial Setup
```bash
# Build image
make build

# Run tests to verify setup
make test
```

### 2. Development
```bash
# Start server with live reload
make dev

# In another terminal, run tests
make test

# Open shell for debugging
make shell
```

### 3. Testing
```bash
# Run all tests
make test

# Run specific tests
docker-compose run --rm test pytest tests/test_auth.py -v

# Check coverage
make test-coverage
```

## Services

### App Server
```bash
# Start
make up

# Access
http://localhost:8000

# API docs
http://localhost:8000/docs
```

### Qdrant (Vector DB)
```bash
# Start with other services
docker-compose up -d qdrant

# Access UI
http://localhost:6333/dashboard
```

### Neo4j (Graph DB)
```bash
# Start with other services
docker-compose up -d neo4j

# Access browser
http://localhost:7474
# Default credentials: neo4j/testpassword
```

## Environment Variables

Create `.env` file in project root:

```bash
# GitHub OAuth (required for auth)
GITHUB_CLIENT_ID=your_client_id
GITHUB_CLIENT_SECRET=your_client_secret
GITHUB_REDIRECT_URI=http://localhost:8000/auth/github/callback

# OpenAI API (optional for tests - mocked)
OPENAI_API_KEY=your_api_key

# Database URLs (optional - mocked in tests)
VECTOR_DB_URL=http://qdrant:6333
GRAPH_DB_URL=bolt://neo4j:7687
GRAPH_DB_PASSWORD=testpassword
```

## Troubleshooting

### Port Already in Use
```bash
# Change port in docker-compose.yml
ports:
  - "8001:8000"  # Use 8001 instead of 8000
```

### Permission Errors
```bash
# Fix data directory permissions
sudo chown -R $USER:$USER data/
```

### Tests Failing
```bash
# Rebuild image
make build

# Run tests with verbose output
docker-compose run --rm test pytest tests/ -v -s
```

### Container Won't Start
```bash
# Check logs
make logs

# Clean and rebuild
make clean
make build
make up
```

## File Structure

```
Clog/
├── Dockerfile              # Container image definition
├── docker-compose.yml      # Multi-service orchestration
├── Makefile               # Convenient commands
├── requirements.txt        # Python dependencies
├── .env                   # Environment variables (create this)
├── src/                   # Application code
├── tests/                 # Test suite
└── data/                  # Persistent data (auto-created)
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build Docker image
        run: docker-compose build
      
      - name: Run tests
        run: docker-compose run --rm test
```

## Benefits

✅ **Isolated environment**: No conflicts with system Python  
✅ **Reproducible**: Same environment everywhere  
✅ **Fast setup**: One command to get started  
✅ **Easy testing**: Run tests without configuration  
✅ **Production-ready**: Same image for dev and prod  

## Next Steps

1. Build image: `make build`
2. Run tests: `make test`
3. Start server: `make up`
4. Open http://localhost:8000/docs

Happy coding! 🚀

