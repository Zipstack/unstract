# Research: Generic Task Queue Abstraction Library

**Phase**: 0 - Research and Analysis
**Date**: 2025-09-14
**Status**: Complete

## Research Summary

This research phase investigated how to create a generic task queue abstraction library ("SQLAlchemy for task queues") that provides a unified interface across Celery, Hatchet, and Temporal backends.

## Decision: Backend Integration Patterns

### Celery Integration
**Approach**: Direct task registration using Celery decorators

**Pattern**:
```python
# TaskBackend.register_task() maps to:
@celery_app.task(name=task_name)
def wrapped_task(*args, **kwargs):
    return original_function(*args, **kwargs)
```

**Rationale**:
- Direct mapping to Celery's task system
- Leverages existing Celery infrastructure (Redis, queues)
- Simple broker-based task submission

### Hatchet Integration
**Approach**: Step-based task registration

**Pattern**:
```python
# TaskBackend.register_task() maps to:
@hatchet_client.step(name=task_name)
async def wrapped_step(context):
    return original_function(*context.args, **context.kwargs)
```

**Rationale**:
- Maps tasks to Hatchet steps
- Can compose steps into workflows later
- Leverages Hatchet's execution engine

### Temporal Integration
**Approach**: Activity-based task registration

**Pattern**:
```python
# TaskBackend.register_task() maps to:
@activity.defn(name=task_name)
async def wrapped_activity(*args, **kwargs):
    return original_function(*args, **kwargs)
```

**Rationale**:
- Maps tasks to Temporal activities
- Activities can be called from workflows
- Leverages Temporal's reliability features

## Worker Patterns

### Celery Workers
**Pattern**: Standard Celery worker process
```python
# In task-backend service:
def run_worker(self):
    self.celery_app.worker_main()
```

### Hatchet Workers
**Pattern**: Hatchet worker polling
```python
# In task-backend service:
def run_worker(self):
    self.hatchet_worker.start()
```

### Temporal Workers
**Pattern**: Temporal worker listening
```python
# In task-backend service:
def run_worker(self):
    await self.temporal_worker.run()
```

## Configuration Patterns

Each backend requires specific configuration:

### Celery Configuration
```yaml
backend: celery
celery:
  broker_url: redis://localhost:6379/0
  result_backend: redis://localhost:6379/0
```

### Hatchet Configuration
```yaml
backend: hatchet
hatchet:
  token: your-hatchet-token
  server_url: https://app.hatchet.run
```

### Temporal Configuration
```yaml
backend: temporal
temporal:
  host: localhost
  port: 7233
  namespace: default
  task_queue: my-queue
```

## Linear Workflow Support (v2)

For sequential task chaining:

### Celery: Chain Pattern
```python
from celery import chain
result = chain(task1.s(), task2.s(), task3.s())()
```

### Hatchet: DAG Pattern
```python
# Tasks with parents create sequential execution
@hatchet.step(parents=["task1"])
def task2(): pass
```

### Temporal: Workflow Calls Activities
```python
@workflow.defn
async def sequential_workflow():
    result1 = await task1()
    result2 = await task2(result1)
    return await task3(result2)
```
