# Shared Worker Infrastructure

This module provides common infrastructure and utilities for lightweight Celery workers that communicate with Django backend via internal APIs instead of direct ORM access.

## Architecture Overview

The shared worker infrastructure enables the creation of lightweight, decoupled Celery workers that:

- **Communicate via HTTP APIs** instead of direct database access
- **Remain independent** of Django ORM and heavy dependencies
- **Provide robust error handling** with retry logic and circuit breakers
- **Include comprehensive monitoring** with health checks and performance metrics
- **Support flexible configuration** via environment variables

## Components

### 1. API Client (`api_client.py`)

HTTP client for communicating with Django backend internal APIs.

**Features:**
- Bearer token authentication
- Automatic retries with exponential backoff
- Request/response logging
- Organization context support
- Standard CRUD operations for workflow executions, webhooks, etc.

**Usage:**
```python
from backend.workers.shared import InternalAPIClient, WorkerConfig

config = WorkerConfig()
with InternalAPIClient(config) as client:
    # Get workflow execution
    execution = client.get_workflow_execution('execution-id')
    
    # Update status
    client.update_workflow_execution_status('execution-id', 'COMPLETED')
    
    # Send webhook
    client.send_webhook('https://example.com/webhook', {'data': 'test'})
```

### 2. Configuration Management (`config.py`)

Centralized configuration with environment variable support.

**Key Settings:**
- `INTERNAL_SERVICE_API_KEY`: API key for authentication
- `DJANGO_APP_BACKEND_URL`: Django backend URL
- `WORKER_NAME`: Worker identifier
- `API_TIMEOUT`: Request timeout
- `LOG_LEVEL`: Logging level

**Usage:**
```python
from backend.workers.shared import WorkerConfig

config = WorkerConfig()
print(f"API URL: {config.internal_api_base_url}")
print(f"Worker: {config.worker_name}")
```

### 3. Retry Logic & Circuit Breakers (`retry_utils.py`)

Robust error handling with multiple retry strategies and circuit breaker pattern.

**Features:**
- Exponential, linear, and fixed backoff strategies
- Configurable retry attempts and delays
- Circuit breaker with failure threshold and recovery timeout
- Jitter to prevent thundering herd

**Usage:**
```python
from backend.workers.shared import retry, circuit_breaker, ResilientExecutor

# Simple retry decorator
@retry(max_attempts=3, base_delay=1.0)
def unreliable_function():
    pass

# Circuit breaker decorator
@circuit_breaker(failure_threshold=5, recovery_timeout=60.0)
def external_service_call():
    pass

# Combined resilient executor
executor = ResilientExecutor()

@executor
def robust_function():
    pass
```

### 4. Logging & Monitoring (`logging_utils.py`)

Structured logging with performance monitoring and context management.

**Features:**
- JSON structured logging
- Thread-local context management
- Performance metrics collection
- Memory usage tracking
- Execution time monitoring

**Usage:**
```python
from backend.workers.shared import WorkerLogger, log_context, monitor_performance

# Configure logging
WorkerLogger.configure(log_level='INFO', log_format='structured')
logger = WorkerLogger.get_logger(__name__)

# Use context manager
with log_context(task_id='123', execution_id='456'):
    logger.info("This will include context")

# Monitor performance
@monitor_performance
def expensive_function():
    pass
```

### 5. Health Checks (`health.py`)

Comprehensive health monitoring with HTTP endpoints.

**Features:**
- API connectivity checks
- System resource monitoring
- Custom health checks
- Health history tracking
- HTTP server for health endpoints

**Usage:**
```python
from backend.workers.shared import HealthChecker, HealthServer

# Initialize health checker
health_checker = HealthChecker(config)

# Add custom check
def custom_check():
    from backend.workers.shared.health import HealthCheckResult, HealthStatus
    return HealthCheckResult("custom", HealthStatus.HEALTHY, "OK")

health_checker.add_custom_check("custom", custom_check)

# Start health server
health_server = HealthServer(health_checker, port=8080)
health_server.start()
```

## Quick Start

### 1. Environment Setup

Create a `.env` file or set environment variables:

```bash
# Required
INTERNAL_SERVICE_API_KEY=your-api-key-here
DJANGO_APP_BACKEND_URL=http://localhost:8000

# Optional
WORKER_NAME=my-worker
LOG_LEVEL=INFO
API_TIMEOUT=30
METRICS_PORT=8080
```

### 2. Create a Worker

```python
import os
from celery import Celery
from backend.workers.shared import (
    WorkerConfig, InternalAPIClient, WorkerLogger, 
    HealthChecker, HealthServer, monitor_performance, retry
)

# Configure logging
WorkerLogger.configure(
    log_level=os.getenv('LOG_LEVEL', 'INFO'),
    log_format='structured',
    worker_name='my-worker'
)

logger = WorkerLogger.get_logger(__name__)
config = WorkerConfig()

# Initialize Celery
app = Celery('my_worker')
app.config_from_object({
    'broker_url': os.getenv('CELERY_BROKER_URL'),
    **config.get_celery_config()
})

# Setup health monitoring
health_checker = HealthChecker(config)
health_server = HealthServer(health_checker, port=config.metrics_port)
health_server.start()

@app.task(bind=True)
@monitor_performance
@retry(max_attempts=3)
def my_task(self, execution_id: str):
    logger.info(f"Processing execution {execution_id}")
    
    with InternalAPIClient(config) as client:
        # Get execution data
        execution = client.get_workflow_execution(execution_id)
        
        # Update status
        client.update_workflow_execution_status(execution_id, 'IN_PROGRESS')
        
        # Do work...
        
        # Update completion
        client.update_workflow_execution_status(execution_id, 'COMPLETED')
    
    return {'status': 'success'}
```

### 3. Run the Worker

```bash
celery -A my_worker worker --loglevel=info -Q my-worker
```

## Health Check Endpoints

When health server is running, these endpoints are available:

- `GET /health` - Full health check
- `GET /health/quick` - Last cached result
- `GET /health/metrics` - System metrics only
- `GET /health/history` - Health check history

Example response:
```json
{
  "status": "healthy",
  "timestamp": "2025-06-24T10:00:00Z",
  "uptime_seconds": 3600,
  "worker_name": "my-worker",
  "checks": {
    "api_connectivity": {"status": "healthy", "message": "API connectivity OK"},
    "system_resources": {"status": "healthy", "message": "System resources OK"},
    "worker_process": {"status": "healthy", "message": "Worker process healthy"}
  }
}
```

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERNAL_SERVICE_API_KEY` | *required* | API key for internal service authentication |
| `DJANGO_APP_BACKEND_URL` | `http://localhost:8000` | Django backend base URL |
| `WORKER_NAME` | `unstract-worker` | Worker identifier |
| `WORKER_VERSION` | `1.0.0` | Worker version |
| `ORGANIZATION_ID` | *none* | Default organization context |
| `API_TIMEOUT` | `30` | API request timeout (seconds) |
| `API_RETRY_ATTEMPTS` | `3` | Number of retry attempts |
| `LOG_LEVEL` | `INFO` | Logging level |
| `LOG_FORMAT` | `structured` | Log format (structured/simple) |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | Circuit breaker failure threshold |
| `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` | `60` | Circuit breaker recovery timeout |
| `HEALTH_CHECK_INTERVAL` | `30` | Health check interval (seconds) |
| `METRICS_PORT` | `8080` | Health server port |
| `MAX_CONCURRENT_TASKS` | `10` | Maximum concurrent tasks |

## Best Practices

### 1. Error Handling
- Always use retry decorators for external API calls
- Implement circuit breakers for unreliable services
- Log errors with context for debugging

### 2. Performance
- Use performance monitoring decorators
- Monitor system resources via health checks
- Set appropriate timeout values

### 3. Logging
- Use structured logging for better searchability
- Include context (task_id, execution_id, org_id)
- Log at appropriate levels (DEBUG/INFO/WARNING/ERROR)

### 4. Health Monitoring
- Implement custom health checks for worker-specific logic
- Monitor health endpoints in production
- Set up alerting based on health status

### 5. Configuration
- Use environment variables for all configuration
- Validate configuration on startup
- Document all configuration options

## Example Workers

See `example_worker.py` for a complete example demonstrating all features of the shared worker infrastructure.

## Testing

To test the shared infrastructure:

1. **Start Django backend** with internal APIs
2. **Configure environment** variables
3. **Run example worker**:
   ```bash
   python -m backend.workers.shared.example_worker
   ```
4. **Check health endpoint**:
   ```bash
   curl http://localhost:8080/health
   ```

## Architecture Benefits

This shared infrastructure provides several key benefits:

1. **Decoupling**: Workers don't depend on Django ORM or database connections
2. **Scalability**: Lightweight workers can be deployed independently
3. **Reliability**: Built-in retry logic and circuit breakers
4. **Observability**: Comprehensive logging and health monitoring
5. **Maintainability**: Shared code reduces duplication
6. **Flexibility**: Easy to configure and extend

## Migration Path

To migrate existing workers to this infrastructure:

1. Replace direct ORM calls with API client calls
2. Add shared infrastructure imports
3. Configure environment variables
4. Update Celery task decorators
5. Add health monitoring
6. Test thoroughly before production deployment
