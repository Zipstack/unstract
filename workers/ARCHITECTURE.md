# Unstract Workers Architecture

## Overview

This package implements lightweight Celery workers that communicate with the Unstract Django backend via internal APIs, eliminating Django ORM dependencies and enabling independent deployment and scaling.

## Architecture Decision

### ✅ **CHOSEN: Clean Microservices Architecture**
```
unstract/
├── workers/              # Independent worker package
│   ├── shared/          # Common utilities (API client, logging, health)
│   ├── api_deployment/  # API deployment worker
│   ├── general/         # General worker (webhooks, general workflows)
│   ├── file_processing/ # File processing worker
│   ├── callback/        # Result aggregation and finalization worker
│   ├── docker/          # Docker configurations
│   ├── scripts/         # Deployment and management scripts
│   └── pyproject.toml   # Independent package definition
└── backend/             # Django backend with internal APIs
```

### ❌ **REJECTED: Backend-Coupled Architecture**
```
backend/
└── workers/             # Workers inside Django backend
    ├── shared/          # Would still have Django coupling risk
    └── ...              # Tight coupling to backend deployment
```

## Benefits of Clean Architecture

### 🎯 **Complete Separation**
- **Zero Django Dependencies**: Workers don't import anything from Django
- **Independent Packaging**: Own `pyproject.toml` with minimal dependencies
- **Microservices Alignment**: Follows existing pattern (`platform-service/`, `prompt-service/`)

### 🚀 **Deployment Flexibility**
- **Independent Versioning**: Workers can be versioned separately from backend
- **Separate Scaling**: Scale workers independently based on workload
- **Different Infrastructure**: Workers can run on different machines/containers
- **Fault Isolation**: Worker failures don't affect Django backend

### 📦 **Resource Efficiency**
- **Minimal Dependencies**: Only essential packages for task processing
- **Smaller Images**: Docker images without Django bloat
- **Faster Startup**: No Django initialization overhead
- **Lower Memory**: ~50MB vs ~200MB for Django workers

## Communication Pattern

```
┌─────────────────┐    HTTP API    ┌──────────────────┐    ORM/DB    ┌──────────────┐
│ Workers         │───────────────→│ Django Backend   │─────────────→│ PostgreSQL   │
│ (Lightweight)   │                │ (Internal APIs)  │               │ Database     │
└─────────────────┘                └──────────────────┘               └──────────────┘
       │                                      │
       ├── Task Coordination                  ├── Business Logic
       ├── Error Handling                     ├── Tool Execution  
       ├── Result Aggregation                 ├── Database Operations
       └── Health Monitoring                  └── Complex Processing
```

## Worker Responsibilities

### **Lightweight Workers Handle:**
- Task orchestration and coordination
- HTTP communication with Django backend
- Error handling and retry logic
- Result aggregation and status tracking
- Health monitoring and metrics collection

### **Django Backend Handles:**
- Complex business logic (tool execution, file processing pipeline)
- Database operations and ORM queries
- Authentication and authorization
- Multi-tenant organization scoping
- Integration with external services

## Package Structure

```
unstract/workers/
├── __init__.py                    # Package interface
├── pyproject.toml                 # Package definition and dependencies
├── README.md                      # Documentation
├── ARCHITECTURE.md                # This file
├── uv.lock                        # Dependency lock file
├── shared/                        # Shared infrastructure
│   ├── __init__.py
│   ├── api_client.py             # Internal API HTTP client
│   ├── config.py                 # Configuration management
│   ├── health.py                 # Health checking system
│   ├── logging_utils.py          # Structured logging
│   └── retry_utils.py            # Circuit breakers and retry logic
├── api_deployment/                # API deployment worker
│   ├── __init__.py
│   ├── worker.py                 # Celery app configuration
│   └── tasks.py                  # async_execute_bin_api task
├── general/                       # General tasks worker
│   ├── __init__.py
│   ├── worker.py                 # Celery app configuration
│   └── tasks.py                  # webhooks, general async_execute_bin
├── file_processing/               # File processing worker
│   ├── __init__.py
│   ├── worker.py                 # Celery app configuration
│   └── tasks.py                  # process_file_batch tasks
├── callback/                      # Result aggregation worker
│   ├── __init__.py
│   ├── worker.py                 # Celery app configuration
│   └── tasks.py                  # process_batch_callback tasks
├── docker/                        # Container configurations
│   ├── api_deployment.Dockerfile
│   ├── general.Dockerfile
│   ├── file_processing.Dockerfile
│   ├── callback.Dockerfile
│   └── docker-compose.workers.yml
├── scripts/                       # Management scripts
│   ├── deploy.sh                 # Deployment automation
│   └── fix_imports.py            # Import path utilities
├── monitoring/                    # Monitoring and metrics
│   └── prometheus_metrics.py     # Prometheus metrics collection
└── config/                        # Configuration
    └── queue_routing.py          # Queue routing and scaling rules
```

## Development Workflow

### **Setup**
```bash
cd unstract/workers
uv sync                          # Install dependencies
```

### **Local Development**
```bash
# Run individual worker
cd api_deployment
python -m worker

# Run with specific queue
celery -A worker worker --loglevel=debug -Q celery_api_deployments
```

### **Testing**
```bash
pytest                           # Run tests
pytest --cov                    # Run with coverage
```

### **Deployment**
```bash
# Deploy all workers
./scripts/deploy.sh --environment production --action deploy

# Deploy specific worker type
./scripts/deploy.sh --workers file --action deploy
```

## Migration Path

1. ✅ **Phase 1**: Created lightweight workers alongside existing heavy workers
2. ✅ **Phase 2**: Implemented file processing and callback workers
3. ✅ **Phase 3**: Moved to clean microservices architecture
4. 🔮 **Future**: Gradual traffic migration and deprecation of heavy workers

## Scalability Benefits

### **Independent Scaling**
- Scale each worker type based on specific workload patterns
- Different concurrency settings per worker type
- Auto-scaling rules based on queue depth

### **Resource Optimization**
- Deploy file processing workers on high-memory nodes
- Deploy callback workers on standard nodes
- Deploy API workers with high network bandwidth

### **Fault Tolerance**
- Worker failures isolated from Django backend
- Circuit breaker patterns prevent cascade failures
- Independent health monitoring and recovery

This architecture provides the foundation for a highly scalable, maintainable, and efficient distributed task processing system for the Unstract platform.
