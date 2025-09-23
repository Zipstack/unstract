# Task Backend Worker Service

A worker management service that uses the `unstract-task-abstraction` library to initialize and run backend-specific workers.

## Architecture

This service is **NOT an HTTP service** - it's a **worker process** that:

1. **Uses task-abstraction library** to get the appropriate backend client
2. **Initializes backend-specific workers** (Celery, Hatchet, Temporal)
3. **Registers workflows** with the selected backend
4. **Runs workers** that consume tasks from the backend

## Backend Types

### Celery Workers
- Connect to Redis broker
- Start multiple worker processes
- Consume from configured queues
- Similar to existing `backend/workers/` pattern

### Hatchet Workers
- Connect to Hatchet server via HTTP/gRPC
- Register workflows with server
- Poll for task assignments
- Execute tasks and report results

### Temporal Workers
- Connect to Temporal server via gRPC
- Register activities and workflows
- Listen for workflow executions
- Handle activity execution

## Usage

```bash
# Install dependencies
uv sync

# Copy configuration
cp sample.env .env
# Edit .env to set TASK_BACKEND_TYPE and connection details

# Start worker (auto-detects backend from env)
task-backend-worker

# Or start specific backend
task-backend-worker --backend=celery
task-backend-worker --backend=hatchet
task-backend-worker --backend=temporal
```

## Configuration

See `sample.env` for all configuration options. Key settings:

- `TASK_BACKEND_TYPE`: Backend to use (celery, hatchet, temporal)
- `CELERY_BROKER_URL`: Redis URL for Celery
- `HATCHET_CLIENT_TOKEN`: Token for Hatchet server
- `TEMPORAL_HOST`: Temporal server host

## Integration with Platform

This service replaces the functionality of:
- Runner Service workers
- Prompt Service workers
- Structure Tool workers

It provides the same task execution capabilities but through a unified, backend-agnostic interface using the task-abstraction library.

## Development

```bash
# Run tests
uv run pytest

# Linting
uv run ruff check .
uv run ruff format .

# Type checking
uv run mypy .
```