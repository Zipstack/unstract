# Data Model: Generic Task Queue Abstraction Library

**Phase**: 1 - Design & Contracts
**Date**: 2025-09-14
**Prerequisites**: Research phase complete

## Core Entities

### TaskBackend (Abstract Interface)
**Purpose**: Core abstraction interface that all backend adapters implement

**Methods**:
- `register_task(fn, name=None)` - Register a function as a task
- `submit(name, *args, **kwargs)` - Submit a task for execution
- `get_result(task_id)` - Retrieve task result by ID
- `run_worker()` - Start the worker loop for this backend

**Properties**:
- `backend_type: str` - Backend identifier (celery, hatchet, temporal)
- `is_connected: bool` - Connection status to backend service

**State Transitions**:
- `Disconnected` → `Connecting` → `Connected` → `Disconnecting` → `Disconnected`

**Validation Rules**:
- Task names must be unique within a backend instance
- Backend must be connected before task submission

### Task
**Purpose**: Individual executable unit registered and submitted for execution

**Properties**:
- `name: str` - Unique task identifier
- `function: Callable` - Python function to execute
- `retry_count: int` - Number of retries attempted
- `timeout: Optional[int]` - Execution timeout in seconds

**States**:
- `Registered` → `Submitted` → `Running` → `Completed` | `Failed`

**Validation Rules**:
- Task name must be unique within backend
- Function must be callable
- Timeout must be positive if specified

### TaskResult
**Purpose**: Standardized result format for task execution across all backends

**Fields**:
- `task_id: str` - Unique execution identifier
- `task_name: str` - Name of executed task
- `status: str` - Execution status (pending, running, completed, failed)
- `result: Any` - Task return value (if completed)
- `error: Optional[str]` - Error message (if failed)
- `started_at: Optional[datetime]` - Execution start time
- `completed_at: Optional[datetime]` - Execution completion time

**Status Values**:
- `"pending"` - Queued for execution
- `"running"` - Currently executing
- `"completed"` - Successfully finished
- `"failed"` - Execution failed

### Backend Implementations

#### CeleryBackend
**Purpose**: Celery task queue adapter implementation

**Configuration**:
- `broker_url: str` - Redis/RabbitMQ broker URL
- `result_backend: str` - Result storage URL
- `task_routes: Dict` - Queue routing configuration

#### HatchetBackend
**Purpose**: Hatchet workflow engine adapter implementation

**Configuration**:
- `token: str` - Hatchet API token
- `server_url: str` - Hatchet server endpoint
- `worker_name: str` - Worker identification

#### TemporalBackend
**Purpose**: Temporal workflow engine adapter implementation

**Configuration**:
- `host: str` - Temporal server host
- `port: int` - Temporal server port
- `namespace: str` - Temporal namespace
- `task_queue: str` - Task queue name

## Configuration Entity

### BackendConfig
**Purpose**: Backend-specific configuration object

**Fields**:
- `backend_type: str` - Backend identifier (celery, hatchet, temporal)
- `connection_params: Dict[str, Any]` - Backend-specific connection settings
- `worker_config: Dict[str, Any]` - Worker-specific settings (concurrency, queues, etc.)

**Validation Rules**:
- Backend type must be supported (celery, hatchet, temporal)
- Connection parameters must include required fields for selected backend
- Configuration must be valid for target backend service

## Workflow Entity (v2 Extension)

### Workflow
**Purpose**: Sequential composition of tasks (linear workflow)

**Properties**:
- `name: str` - Unique workflow identifier
- `tasks: List[str]` - Ordered list of task names to execute
- `description: Optional[str]` - Workflow description

**Execution**:
- Tasks execute in order: task[0] → task[1] → task[2] → ...
- Output of task[n] becomes input to task[n+1]
- Workflow fails if any task fails

**Backend Mapping**:
- **Celery**: Uses `chain()` to link tasks sequentially
- **Hatchet**: Creates DAG with ordered dependencies
- **Temporal**: Workflow calls activities in sequence

---

## Summary

The data model focuses on simple, clean abstractions:
- **TaskBackend**: Core interface
- **Task**: Individual executable functions
- **TaskResult**: Standardized results
- **BackendConfig**: Configuration
- **Workflow**: Linear task sequences (v2)

All complex orchestration, migration, and monitoring features are intentionally excluded to maintain simplicity.
