# Final Architecture: Task Abstraction Library

**Implementation**: Complete
**Date**: 2025-09-15
**Status**: Production Ready

## 🏗️ **System Architecture**

### **Core Philosophy: "SQLAlchemy for Task Queues"**
Clean, minimal abstraction layer that provides unified interface over existing task queue engines without reimplementing their features.

## 📦 **Component Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                        │
├─────────────────────────────────────────────────────────────┤
│  @backend.register_task                                     │
│  backend.submit("task_name", args)                          │
│  result = backend.get_result(task_id)                       │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│              TASK ABSTRACTION LAYER                         │
├─────────────────────────────────────────────────────────────┤
│  • TaskBackend (abstract interface)                        │
│  • TaskResult (unified result model)                       │
│  • BackendConfig (environment-driven config)               │
│  • WorkflowDefinition (sequential patterns)                │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│                BACKEND ADAPTERS                             │
├─────────────────────────────────────────────────────────────┤
│  CeleryBackend  │  HatchetBackend  │  TemporalBackend       │
│  • register()   │  • register()    │  • register()          │
│  • submit()     │  • submit()      │  • submit()            │
│  • get_result() │  • get_result()  │  • get_result()        │
│  • run_worker() │  • run_worker()  │  • run_worker()        │
└─────────────────┬───────────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────────┐
│              NATIVE BACKEND ENGINES                         │
├─────────────────────────────────────────────────────────────┤
│      Celery     │     Hatchet      │      Temporal          │
│  • Retries      │  • Retries       │  • Retries             │
│  • DLQ          │  • DLQ           │  • DLQ                 │
│  • Persistence  │  • Persistence   │  • Persistence         │
│  • Monitoring   │  • Monitoring    │  • Monitoring          │
│  • Scaling      │  • Scaling       │  • Scaling             │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 **Design Principles**

### 1. **Minimal Interface**
```python
# Only 4 core operations
backend.register_task(fn)
backend.submit(name, *args, **kwargs)
backend.get_result(task_id)
backend.run_worker()
```

### 2. **Backend Delegation**
```python
# All production features handled by backends
"""
Note: Resilience (retries, DLQ, persistence) is handled by the backend.
Configure these features in your Celery/Temporal/Hatchet setup.
"""
```

### 3. **Environment-Driven Configuration**
```bash
# Single variable switches entire backend
TASK_BACKEND_TYPE=celery    # Uses Celery
TASK_BACKEND_TYPE=temporal  # Uses Temporal
TASK_BACKEND_TYPE=hatchet   # Uses Hatchet
```

## 🔧 **Implementation Details**

### **Task Abstraction Library Structure**
```
unstract/task-abstraction/
├── src/unstract/task_abstraction/
│   ├── __init__.py          # Main exports: get_backend, TASK_REGISTRY
│   ├── base.py              # TaskBackend abstract class
│   ├── factory.py           # Backend factory with auto-detection
│   ├── models.py            # TaskResult, BackendConfig models
│   ├── workflow.py          # Sequential workflow patterns
│   ├── backends/
│   │   ├── celery.py        # Celery adapter implementation
│   │   ├── hatchet.py       # Hatchet adapter implementation
│   │   └── temporal.py      # Temporal adapter implementation
│   └── tasks/
│       ├── core/            # Core task definitions
│       │   ├── basic_operations.py
│       │   ├── data_processing.py
│       │   └── system_tasks.py
│       └── enterprise/      # Enterprise tasks (build-time)
│           ├── llm_tasks.py
│           ├── analytics_tasks.py
│           └── connector_tasks.py
```

### **Task-Backend Worker Service Structure**
```
task-backend/
├── src/unstract/task_backend/
│   ├── worker.py            # Main TaskBackendWorker class
│   ├── config.py            # Configuration management
│   ├── cli/
│   │   └── main.py          # CLI interface and argument parsing
│   └── health.py            # Health check endpoints
└── test_*.py                # Test scripts and validation
```

## 📊 **Data Flow**

### **Task Registration Flow**
```
1. Application imports TASK_REGISTRY
2. Worker calls backend.register_task(fn) for each task
3. Backend adapter registers with native engine
4. Worker starts native engine worker loop
```

### **Task Execution Flow**
```
1. Application calls backend.submit("task_name", args)
2. Backend adapter submits to native engine
3. Native engine queues and executes task
4. Application polls backend.get_result(task_id)
5. Backend adapter queries native engine
6. Returns unified TaskResult model
```

### **Backend Switching Flow**
```
1. Set TASK_BACKEND_TYPE environment variable
2. get_backend() auto-detects and creates appropriate adapter
3. Same application code works with new backend
4. All resilience configured in new backend's native config
```

## 🔐 **Configuration Management**

### **Environment Variables**
```bash
# Required
TASK_BACKEND_TYPE=celery|hatchet|temporal

# Optional (dev convenience)
TASK_QUEUES=queue1,queue2,queue3  # Only in non-prod environments

# Backend-specific (passed through to native engines)
CELERY_BROKER_URL=redis://localhost:6379
TEMPORAL_HOST=localhost:7233
HATCHET_CLIENT_TOKEN=token_here
```

### **Worker Configuration**
```bash
# Production deployment (explicit queue specification)
uv run task-backend-worker --queues file_processing,api_processing

# Development (can use env var)
TASK_QUEUES=file_processing,api_processing uv run task-backend-worker

# Backend override
uv run task-backend-worker --backend celery --queues file_processing
```

## 🎯 **Workflow Support**

### **Sequential Patterns**
```python
# Decorator-based workflow definition
@workflow(backend)
def data_pipeline():
    return [
        ("extract_data", {"source": "database"}),
        "transform_data",
        ("load_data", {"target": "warehouse"})
    ]

# Pattern-based workflow definition
workflow = WorkflowDefinition.sequential([
    ("validate_input", {}),
    "process_data",
    ("save_results", {"format": "json"})
])

backend.register_workflow(workflow)
workflow_id = backend.submit_workflow("data_pipeline", initial_data)
```

### **Workflow Execution**
```python
# Simple sequential execution
class WorkflowExecutor:
    def execute_workflow_patterns(self, workflow_def, initial_input):
        current_result = initial_input
        for step in workflow_def.steps:
            task_id = self.backend.submit(step.task_name, current_result, **step.kwargs)
            result = self.backend.get_result(task_id)  # Backend handles polling
            current_result = result.result
        return current_result
```

## 🧪 **Testing Strategy**

### **Test Coverage**
```
task-backend/
├── test_simple.py           # Basic task execution
├── test_tasks.py            # Task registration and execution
├── test_workflow.py         # Task chaining and Celery chains
└── test_workflow_patterns.py # Sequential workflow patterns

unstract/task-abstraction/tests/
├── unit/                    # Unit tests for individual components
├── integration/             # Cross-backend integration tests
└── contract/                # Backend adapter contract tests
```

### **Verification Scenarios**
- ✅ Task registration and execution across all backends
- ✅ Backend switching without code changes
- ✅ Sequential workflow execution
- ✅ Worker deployment with queue specification
- ✅ Error handling and result consistency

## 🚀 **Deployment Architecture**

### **Development Deployment**
```bash
# Single worker for all tasks
TASK_BACKEND_TYPE=celery
TASK_QUEUES=file_processing,api_processing
uv run task-backend-worker
```

### **Production Deployment**
```bash
# Specialized workers per queue
uv run task-backend-worker --queues file_processing
uv run task-backend-worker --queues api_processing
uv run task-backend-worker --queues callback_processing

# Auto-generated worker names
worker-server01-file_processing
worker-server02-api_processing
worker-server03-callback_processing
```

### **Backend-Specific Production Config**
```python
# Celery production setup
CELERY_TASK_RETRY_DELAY = 60
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_RESULT_EXPIRES = 3600

# Temporal production setup
task_retry_policy = RetryPolicy(maximum_attempts=3)
task_timeout = timedelta(minutes=5)

# Hatchet production setup
@hatchet.workflow(timeout="5m", retries=3)
```

## 📈 **Performance Characteristics**

### **Overhead Analysis**
- **Abstraction Layer**: Minimal - just interface delegation
- **Task Registration**: One-time startup cost per task
- **Task Execution**: Single additional function call per submit/get_result
- **Memory Usage**: Negligible - no state persistence in abstraction

### **Scalability**
- **Horizontal**: Scales with backend's native scaling (unlimited)
- **Backend Switching**: Zero downtime with proper deployment
- **Queue Management**: Leverages backend's native queue routing

## 🔮 **Evolution Path**

### **Current Version (v1.0)**
- ✅ Core task abstraction
- ✅ Sequential workflows
- ✅ Three backend support

### **Future Enhancements (v2+)**
- Enhanced workflow patterns
- Additional backend implementations
- Improved error normalization
- Advanced task registry features

### **Never In Scope**
- Custom DLQ implementation
- State persistence layer
- Monitoring/observability system
- Worker management system

---

**Architecture Status**: ✅ **COMPLETE AND PRODUCTION READY**
**Philosophy**: Clean abstraction over proven engines
**Motto**: "Configure production features in your backend, not in the abstraction"