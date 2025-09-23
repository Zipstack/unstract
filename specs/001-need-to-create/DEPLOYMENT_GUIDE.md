# Production Deployment Guide: Task Abstraction Library

**System**: Task Abstraction Library + Task-Backend Service
**Status**: Production Ready
**Date**: 2025-09-15

## 🚀 **Quick Start Production Deployment**

### **Step 1: Choose Your Backend**
```bash
# For existing Celery infrastructure
export TASK_BACKEND_TYPE=celery

# For new Temporal deployment
export TASK_BACKEND_TYPE=temporal

# For Hatchet workflows
export TASK_BACKEND_TYPE=hatchet
```

### **Step 2: Install the Libraries**
```bash
# Install task abstraction library
cd unstract/task-abstraction
uv sync
pip install -e .

# Install task backend service
cd task-backend
uv sync
pip install -e .
```

### **Step 3: Configure Backend Production Features**
Configure resilience features in your chosen backend's native configuration.

### **Step 4: Deploy Workers**
```bash
# Production deployment with explicit queue specification
uv run task-backend-worker --queues file_processing,api_processing
```

### **Step 5: Use the Abstraction**
```python
# Your application code - works with any backend
from unstract.task_abstraction import get_backend

backend = get_backend()
task_id = backend.submit("process_document", document_data)
result = backend.get_result(task_id)
```

## 🔧 **Backend-Specific Configuration**

### **Celery Production Setup**

#### **Required Environment Variables**
```bash
export TASK_BACKEND_TYPE=celery
export CELERY_BROKER_URL=redis://redis-cluster:6379/0
export CELERY_RESULT_BACKEND=redis://redis-cluster:6379/1
```

#### **Production Configuration**
```python
# celeryconfig.py
task_retry_delay = 60                 # Wait 60s between retries
task_max_retries = 3                  # Max 3 retry attempts
task_result_expires = 3600            # Results expire after 1 hour
worker_prefetch_multiplier = 1        # One task per worker at a time
task_acks_late = True                 # Acknowledge after completion
worker_disable_rate_limits = False    # Enable rate limiting
task_reject_on_worker_lost = True     # Reject tasks on worker crash

# Dead Letter Queue
task_routes = {
    '*': {'queue': 'default'},
    'failed_tasks': {'queue': 'dlq'}
}
```

#### **Worker Deployment**
```bash
# Specialized workers per queue
uv run task-backend-worker --queues file_processing --concurrency 4
uv run task-backend-worker --queues api_processing --concurrency 8
uv run task-backend-worker --queues callback_processing --concurrency 2
```

### **Temporal Production Setup**

#### **Required Environment Variables**
```bash
export TASK_BACKEND_TYPE=temporal
export TEMPORAL_HOST=temporal.company.com:7233
export TEMPORAL_NAMESPACE=production
```

#### **Production Configuration**
```python
# temporal_config.py
from datetime import timedelta
from temporalio.common import RetryPolicy

task_retry_policy = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=60),
    maximum_interval=timedelta(minutes=10),
    backoff_coefficient=2.0
)

task_timeout = timedelta(minutes=5)
workflow_timeout = timedelta(hours=1)
```

#### **Worker Deployment**
```bash
# Temporal workers with task queue specification
uv run task-backend-worker --queues file_processing_queue --concurrency 10
uv run task-backend-worker --queues api_processing_queue --concurrency 20
```

### **Hatchet Production Setup**

#### **Required Environment Variables**
```bash
export TASK_BACKEND_TYPE=hatchet
export HATCHET_CLIENT_TOKEN=your_token_here
export HATCHET_SERVER_URL=https://hatchet.company.com
```

#### **Production Configuration**
```python
# hatchet_config.py
@hatchet.workflow(
    name="production_workflow",
    timeout="5m",
    retries=3,
    schedule_timeout="1h"
)
```

#### **Worker Deployment**
```bash
# Hatchet workers mapped to workflows
uv run task-backend-worker --queues file_processing_workflow --concurrency 5
uv run task-backend-worker --queues api_processing_workflow --concurrency 10
```

## 🏭 **Production Architecture Patterns**

### **Pattern 1: Queue-Based Deployment**
```bash
# Separate workers for different workload types
# File processing (CPU intensive)
uv run task-backend-worker --queues file_processing --concurrency 2

# API processing (I/O intensive)
uv run task-backend-worker --queues api_processing --concurrency 8

# Callbacks (low latency)
uv run task-backend-worker --queues callback_processing --concurrency 4
```

### **Pattern 2: Environment-Based Deployment**
```bash
# Development
export TASK_BACKEND_TYPE=celery
export TASK_QUEUES=file_processing,api_processing  # Dev convenience
uv run task-backend-worker

# Staging
export TASK_BACKEND_TYPE=temporal
uv run task-backend-worker --queues staging_file_processing

# Production
export TASK_BACKEND_TYPE=temporal
uv run task-backend-worker --queues prod_file_processing,prod_api_processing
```

### **Pattern 3: Hybrid Backend Deployment**
```bash
# Legacy tasks on Celery
TASK_BACKEND_TYPE=celery uv run task-backend-worker --queues legacy_processing

# New tasks on Temporal
TASK_BACKEND_TYPE=temporal uv run task-backend-worker --queues new_processing
```

## 🔍 **Monitoring and Observability**

### **Application-Level Monitoring**
```python
# Application code with logging
import logging
logger = logging.getLogger(__name__)

backend = get_backend()
logger.info(f"Using backend: {backend.backend_type}")

task_id = backend.submit("process_document", document_data)
logger.info(f"Submitted task: {task_id}")

result = backend.get_result(task_id)
if result.status == 'completed':
    logger.info(f"Task completed: {task_id}")
else:
    logger.error(f"Task failed: {task_id}, error: {result.error}")
```

### **Backend-Specific Monitoring**

#### **Celery Monitoring**
```bash
# Celery Flower for web UI
pip install flower
celery flower --broker=redis://redis-cluster:6379/0

# Celery events monitoring
celery events --broker=redis://redis-cluster:6379/0
```

#### **Temporal Monitoring**
```bash
# Temporal Web UI (built-in)
# Access at: http://temporal.company.com:8088

# Temporal CLI monitoring
temporal workflow list --namespace production
temporal workflow show --workflow-id workflow_123
```

#### **Hatchet Monitoring**
```bash
# Hatchet Dashboard (built-in)
# Access at: https://hatchet.company.com/dashboard

# Hatchet CLI monitoring
hatchet workflow list
hatchet workflow status workflow_123
```

## 🛡️ **Security Configuration**

### **Network Security**
```bash
# Redis/Broker security
export CELERY_BROKER_URL=rediss://username:password@redis-cluster:6380/0
export CELERY_RESULT_BACKEND=rediss://username:password@redis-cluster:6380/1

# Temporal TLS
export TEMPORAL_TLS_CERT_PATH=/path/to/cert.pem
export TEMPORAL_TLS_KEY_PATH=/path/to/key.pem

# Hatchet API tokens
export HATCHET_CLIENT_TOKEN=your_secure_token_here
```

### **Task Security**
```python
# Secure task definitions
@backend.register_task
def process_sensitive_data(encrypted_data: str) -> str:
    # Decrypt data within task
    data = decrypt(encrypted_data)
    processed = process(data)
    # Return encrypted result
    return encrypt(processed)
```

## 📊 **Performance Tuning**

### **Worker Concurrency**
```bash
# CPU-bound tasks (lower concurrency)
uv run task-backend-worker --queues file_processing --concurrency 2

# I/O-bound tasks (higher concurrency)
uv run task-backend-worker --queues api_processing --concurrency 16

# Mixed workload (medium concurrency)
uv run task-backend-worker --queues mixed_processing --concurrency 8
```

### **Backend-Specific Tuning**

#### **Celery Performance**
```python
# celeryconfig.py
worker_prefetch_multiplier = 1        # Prevent task hoarding
task_compression = 'gzip'             # Compress large payloads
result_compression = 'gzip'           # Compress results
worker_max_tasks_per_child = 100      # Prevent memory leaks
```

#### **Temporal Performance**
```python
# temporal_config.py
max_cached_workflows = 100            # Workflow cache size
max_concurrent_activities = 100       # Activity concurrency
max_concurrent_workflow_tasks = 100   # Workflow task concurrency
```

#### **Hatchet Performance**
```python
# hatchet_config.py
@hatchet.workflow(
    max_runs=100,                     # Max concurrent runs
    schedule_timeout="30s"            # Schedule timeout
)
```

## 🚨 **Troubleshooting**

### **Common Issues**

#### **Backend Not Found**
```bash
# Error: Backend 'celery' not available
# Solution: Install backend dependencies
pip install celery[redis]  # For Celery
pip install temporalio     # For Temporal
pip install hatchet-sdk    # For Hatchet
```

#### **Queue Configuration**
```bash
# Error: No queues specified for production deployment
# Solution: Always specify queues in production
uv run task-backend-worker --queues file_processing,api_processing
```

#### **Task Registration**
```python
# Error: Task 'my_task' not registered
# Solution: Ensure task is in TASK_REGISTRY
from unstract.task_abstraction import TASK_REGISTRY
print([task.__name__ for task in TASK_REGISTRY])  # Check registered tasks
```

### **Debugging Commands**
```bash
# Check worker status
uv run task-backend-worker --help

# Test task execution
python -c "
from unstract.task_abstraction import get_backend
backend = get_backend()
print(f'Backend: {backend.backend_type}')
"

# Check backend configuration
python -c "
from unstract.task_abstraction import get_backend
backend = get_backend()
print(f'Config: {backend.config}')
"
```

## 🔄 **Migration Strategies**

### **Gradual Migration from Existing Backend**
```python
# Phase 1: Parallel deployment
# Keep existing Celery workers running
# Deploy new task-abstraction workers for new tasks

# Phase 2: Task-by-task migration
# Move tasks one by one to task-abstraction
# Test thoroughly in staging

# Phase 3: Full migration
# Switch all tasks to task-abstraction
# Decommission old workers
```

### **Backend Switching**
```bash
# Zero-downtime backend switch
# 1. Deploy new backend workers
uv run task-backend-worker --backend temporal --queues file_processing

# 2. Update application configuration
export TASK_BACKEND_TYPE=temporal

# 3. Restart application services
# 4. Shutdown old backend workers
```

## ✅ **Production Checklist**

### **Pre-Deployment**
- [ ] Backend dependencies installed
- [ ] Environment variables configured
- [ ] Backend production features configured (retries, DLQ, timeouts)
- [ ] Worker deployment strategy planned
- [ ] Monitoring setup configured
- [ ] Security configuration reviewed

### **Deployment**
- [ ] Workers deployed with explicit queue specification
- [ ] Application services updated with backend configuration
- [ ] Monitoring dashboards accessible
- [ ] Log aggregation configured
- [ ] Health checks passing

### **Post-Deployment**
- [ ] Task execution verified across all queues
- [ ] Error handling tested
- [ ] Performance metrics baseline established
- [ ] Alerting rules configured
- [ ] Runbook documentation updated

---

**Deployment Status**: ✅ **READY FOR PRODUCTION**
**Support**: Configure backend-native features for production resilience
**Philosophy**: "Clean abstraction over proven engines"