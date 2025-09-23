# Flexible Worker Deployment Design

## Current Backend Pattern Analysis

The current backend supports multiple worker patterns:

```bash
# Different queues for different purposes
celery -A backend worker -Q celery --autoscale 4,1
celery -A backend worker -Q celery_api_deployments --autoscale 4,1
celery -A backend.workers.file_processing worker -Q file_processing --autoscale 4,1
celery -A backend.workers.file_processing_callback worker -Q file_processing_callback --autoscale 4,1
```

## Required Flexibility Patterns

### 1. **Task Grouping Flexibility**
- **Dedicated Worker**: Task A gets its own worker deployment
- **Combined Worker**: Tasks B+C share one worker deployment
- **Queue-based**: Multiple workers consuming same queue for scaling

### 2. **Resource Flexibility**
- **High Memory**: Dedicated worker with 8GB RAM
- **Low Memory**: Lightweight worker with 512MB RAM
- **CPU Intensive**: Worker with more CPU allocation
- **I/O Intensive**: Worker optimized for I/O operations

### 3. **Deployment Flexibility**
- **Separate K8s Deployments**: Each worker type as separate deployment
- **Shared Deployments**: Multiple task types in same deployment
- **Auto-scaling**: Different scaling rules per worker type

## Solution Design

### Enhanced task-backend Worker

```bash
# Current (limited)
task-backend-worker --backend=celery

# Enhanced (flexible)
task-backend-worker --backend=celery --tasks=file_processing,data_validation
task-backend-worker --backend=celery --tasks=api_tasks --queues=api_high_priority,api_low_priority
task-backend-worker --backend=celery --exclude-tasks=heavy_ml_tasks
task-backend-worker --backend=celery --worker-profile=high-memory
```

### Configuration Patterns

#### 1. **Task-Based Worker Filtering**
```python
# Register only specific tasks
@task_filter(["file_processing", "data_validation"])
class FileProcessingWorker:
    def register_tasks(self):
        # Only registers allowed tasks
        for task in TASK_REGISTRY:
            if task.__name__ in self.allowed_tasks:
                self.backend.register_task(task)
```

#### 2. **Queue-Based Routing**
```python
# Celery: Different queues for different workers
@backend.register_task(queue="high_priority")
def urgent_task():
    pass

@backend.register_task(queue="batch_processing")
def batch_task():
    pass
```

#### 3. **Worker Profiles**
```yaml
# worker-profiles.yaml
profiles:
  high-memory:
    tasks: ["ml_training", "large_data_processing"]
    queues: ["ml_queue"]
    concurrency: 2
    resources:
      memory: "8Gi"
      cpu: "4"

  lightweight:
    tasks: ["api_tasks", "notifications"]
    queues: ["api_queue", "notification_queue"]
    concurrency: 10
    resources:
      memory: "512Mi"
      cpu: "500m"

  file-processing:
    tasks: ["file_extract", "file_transform"]
    queues: ["file_queue"]
    concurrency: 4
    resources:
      memory: "2Gi"
      cpu: "1"
```

## Implementation Strategy

### Phase 1: Basic Task Filtering
```python
class TaskBackendWorker:
    def __init__(self, backend_type=None, tasks=None, exclude_tasks=None):
        self.allowed_tasks = set(tasks) if tasks else None
        self.excluded_tasks = set(exclude_tasks) if exclude_tasks else set()

    def _register_tasks(self):
        for task_func in TASK_REGISTRY:
            task_name = task_func.__name__

            # Skip if not in allowed list
            if self.allowed_tasks and task_name not in self.allowed_tasks:
                continue

            # Skip if in excluded list
            if task_name in self.excluded_tasks:
                continue

            self.backend.register_task(task_func)
```

### Phase 2: Queue-Based Routing
```python
# Enhanced task registration with queue routing
@backend.register_task(queue="file_processing")
def extract_data():
    pass

# Worker starts with specific queues
task-backend-worker --backend=celery --queues=file_processing,data_validation
```

### Phase 3: Worker Profiles
```python
# Load profile configuration
task-backend-worker --backend=celery --profile=high-memory
```

## Kubernetes Deployment Examples

### Separate Deployments for Different Tasks

```yaml
# file-processing-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-worker-file-processing
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: worker
        image: task-backend:latest
        command: ["task-backend-worker"]
        args: ["--backend=celery", "--tasks=file_extract,file_transform"]
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
          limits:
            memory: "4Gi"
            cpu: "2"
        env:
        - name: TASK_BACKEND_TYPE
          value: "celery"

---
# api-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-worker-api
spec:
  replicas: 5
  template:
    spec:
      containers:
      - name: worker
        image: task-backend:latest
        command: ["task-backend-worker"]
        args: ["--backend=celery", "--tasks=api_process,webhook_send"]
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
        env:
        - name: TASK_BACKEND_TYPE
          value: "celery"

---
# ml-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-worker-ml
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: worker
        image: task-backend:latest
        command: ["task-backend-worker"]
        args: ["--backend=celery", "--tasks=ml_training,model_inference"]
        resources:
          requests:
            memory: "8Gi"
            cpu: "4"
          limits:
            memory: "16Gi"
            cpu: "8"
        env:
        - name: TASK_BACKEND_TYPE
          value: "celery"
```

### Helm Values for Flexibility

```yaml
# values.yaml
taskConfig: &taskConfig
  backend_type: "celery"
  broker_url: "redis://redis:6379/0"

workers:
  file-processing:
    enabled: true
    replicas: 3
    tasks: ["file_extract", "file_transform", "file_validate"]
    resources:
      requests: { memory: "2Gi", cpu: "1" }
      limits: { memory: "4Gi", cpu: "2" }
    autoscaling:
      enabled: true
      minReplicas: 2
      maxReplicas: 10

  api-tasks:
    enabled: true
    replicas: 5
    tasks: ["api_process", "webhook_send", "notification_send"]
    resources:
      requests: { memory: "512Mi", cpu: "250m" }
      limits: { memory: "1Gi", cpu: "500m" }
    autoscaling:
      enabled: true
      minReplicas: 3
      maxReplicas: 20

  ml-processing:
    enabled: false  # Can be disabled
    replicas: 1
    tasks: ["ml_training", "model_inference"]
    resources:
      requests: { memory: "8Gi", cpu: "4" }
      limits: { memory: "16Gi", cpu: "8" }
    nodeSelector:
      workload-type: "ml"  # Special nodes for ML
```

## Benefits

1. **🎯 Infra Flexibility** - Each task can have dedicated resources
2. **📈 Independent Scaling** - Scale file processing vs API tasks separately
3. **💰 Cost Optimization** - Right-size resources per workload
4. **🔧 Operational Control** - Deploy/restart workers independently
5. **🚀 Performance** - Isolate heavy tasks from lightweight ones
6. **📊 Monitoring** - Separate metrics per worker type

## Migration Strategy

1. **Phase 1**: Implement basic task filtering (--tasks flag)
2. **Phase 2**: Add queue-based routing for Celery
3. **Phase 3**: Add worker profiles with resource specifications
4. **Phase 4**: Helm chart with flexible worker deployments

This ensures we're prepared for any infrastructure requirement!