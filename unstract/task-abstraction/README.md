# Unstract Task Abstraction

A unified task queue abstraction layer for the Unstract platform that provides "SQLAlchemy for task queues" - a simple, clean abstraction over different task queue backends.

## Philosophy

Like SQLAlchemy provides a unified interface over different databases while delegating database-specific features to the underlying engine, this abstraction provides a unified task API while delegating production resilience to the underlying task queue backend.

## Features

- **Backend Agnostic**: Switch between Celery, Hatchet, and Temporal without code changes
- **Environment-Driven**: Auto-detects backend from `TASK_BACKEND_TYPE` environment variable
- **Minimal Interface**: Simple `submit()` and `get_result()` API with optional workflow patterns
- **Resilience Delegation**: Production features (retries, DLQ, persistence) handled by backend

## Quick Start

```python
import os
from unstract.task_abstraction import get_backend

# Set backend type
os.environ["TASK_BACKEND_TYPE"] = "celery"

# Get backend instance (auto-detects from environment)
backend = get_backend()

# Register a task
@backend.register_task
def add_numbers(a: int, b: int) -> int:
    return a + b

# Submit task
task_id = backend.submit("add_numbers", 15, 25)

# Get result
result = backend.get_result(task_id)
print(f"Result: {result}")
```

## Supported Backends

- **Celery**: Production-ready distributed task queue
- **Hatchet**: Modern workflow engine with DAG support
- **Temporal**: Reliable workflow orchestration platform

## Production Resilience

**The abstraction does NOT implement resilience features.** Instead, configure these in your chosen backend:

### Celery Configuration
```python
# Configure retries, DLQ, and persistence in Celery
@app.task(autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def my_task():
    pass

# Configure dead letter queue
CELERY_ROUTES = {
    'my_task': {'routing_key': 'my_queue'},
}
```

### Temporal Configuration
```python
# Configure retries and persistence in Temporal
@workflow.activity(retry_policy=RetryPolicy(
    maximum_attempts=3,
    backoff_coefficient=2.0
))
async def my_activity():
    pass
```

### Hatchet Configuration
```yaml
# Configure resilience in Hatchet workflow definition
steps:
  - name: my_step
    retries: 3
    timeout: 30s
```

**Why this approach?**
- Backends already provide battle-tested resilience features
- Avoids reimplementing distributed systems primitives
- Keeps abstraction lean and focused
- Leverages backend-specific optimizations

## Installation

```bash
# Basic installation
pip install unstract-task-abstraction

# With specific backend support
pip install "unstract-task-abstraction[celery]"
pip install "unstract-task-abstraction[hatchet]"
pip install "unstract-task-abstraction[temporal]"
pip install "unstract-task-abstraction[all]"
```

## Configuration

Set the backend type via environment variable:

```bash
export TASK_BACKEND_TYPE=celery
export TASK_CELERY_BROKER_URL=redis://localhost:6379/0
export TASK_CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

## Documentation

For complete documentation, visit: https://docs.unstract.com