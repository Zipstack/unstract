# Flexible Worker Deployment Examples

## Current Task Registry
Our task-backend has these tasks available:
- `health_check` - Simple health check task
- `echo` - Echo task for testing
- `add_numbers` - Arithmetic task (sum of 2 numbers)
- `process_data` - Generic data processing
- `simulate_work` - Simulates work with sleep

## Worker Deployment Patterns

### 1. All Tasks (Default)
```bash
# Registers all tasks
task-backend-worker --backend=celery
```
**Registers**: health_check, echo, add_numbers, process_data, simulate_work

### 2. Specific Tasks Only
```bash
# Only registers arithmetic and data processing tasks
task-backend-worker --backend=celery --tasks=add_numbers,process_data
```
**Registers**: add_numbers, process_data
**Skips**: health_check, echo, simulate_work

### 3. Exclude Heavy Tasks
```bash
# Excludes the long-running simulate_work task
task-backend-worker --backend=celery --exclude-tasks=simulate_work
```
**Registers**: health_check, echo, add_numbers, process_data
**Skips**: simulate_work

### 4. Lightweight Worker (API tasks)
```bash
# Only fast, lightweight tasks
task-backend-worker --backend=celery --tasks=health_check,echo,add_numbers
```
**Registers**: health_check, echo, add_numbers
**Skips**: process_data, simulate_work

### 5. Data Processing Worker
```bash
# Only data processing tasks
task-backend-worker --backend=celery --tasks=process_data,simulate_work
```
**Registers**: process_data, simulate_work
**Skips**: health_check, echo, add_numbers

## Kubernetes Deployment Examples

### File Processing Worker
```yaml
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
        args: ["--tasks=process_data"]
        resources:
          requests:
            memory: "2Gi"
            cpu: "1"
        env:
        - name: TASK_BACKEND_TYPE
          value: "celery"
```

### API Worker (Fast Tasks)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-worker-api
spec:
  replicas: 10
  template:
    spec:
      containers:
      - name: worker
        image: task-backend:latest
        command: ["task-backend-worker"]
        args: ["--tasks=health_check,echo,add_numbers"]
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
        env:
        - name: TASK_BACKEND_TYPE
          value: "celery"
```

### Heavy Processing Worker
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: task-worker-heavy
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: worker
        image: task-backend:latest
        command: ["task-backend-worker"]
        args: ["--tasks=simulate_work"]
        resources:
          requests:
            memory: "4Gi"
            cpu: "2"
        env:
        - name: TASK_BACKEND_TYPE
          value: "celery"
```

## Real-World Scenarios

### Scenario 1: API Response Time SLA
**Requirement**: API tasks must respond in <100ms
**Solution**:
```bash
# Fast API worker
task-backend-worker --tasks=health_check,echo,add_numbers --backend=celery

# Separate heavy processing worker
task-backend-worker --tasks=process_data,simulate_work --backend=celery
```

### Scenario 2: Resource Constraints
**Requirement**: Limited memory nodes vs high-memory nodes
**Solution**:
```bash
# Lightweight worker (512MB nodes)
task-backend-worker --tasks=health_check,echo --backend=celery

# Heavy worker (8GB nodes)
task-backend-worker --tasks=process_data,simulate_work --backend=celery
```

### Scenario 3: Different SLAs
**Requirement**: Different reliability requirements
**Solution**:
```bash
# Critical tasks (high availability)
task-backend-worker --tasks=health_check,add_numbers --backend=celery

# Best-effort tasks (lower availability)
task-backend-worker --tasks=simulate_work --backend=celery
```

## Testing the Implementation

### Test Task Filtering
```python
#!/usr/bin/env python3
"""Test script for task filtering functionality."""

import os
from unstract.task_abstraction import get_backend

def test_task_filtering():
    """Test different task filtering scenarios."""

    # Set environment
    os.environ["TASK_BACKEND_TYPE"] = "celery"

    print("🧪 Testing Task Filtering")
    print("=" * 50)

    # Test 1: Submit to filtered worker
    backend = get_backend()

    try:
        # This will work if add_numbers is registered
        task_id = backend.submit("add_numbers", 15, 25)
        print(f"✅ add_numbers task submitted: {task_id}")
    except Exception as e:
        print(f"❌ add_numbers failed: {e}")

    try:
        # This might fail if simulate_work is excluded
        task_id = backend.submit("simulate_work", 2)
        print(f"✅ simulate_work task submitted: {task_id}")
    except Exception as e:
        print(f"❌ simulate_work failed (probably filtered): {e}")

if __name__ == "__main__":
    test_task_filtering()
```

### Run Different Worker Configurations
```bash
# Terminal 1: All tasks
TASK_BACKEND_TYPE=celery task-backend-worker

# Terminal 2: Only arithmetic tasks
TASK_BACKEND_TYPE=celery task-backend-worker --tasks=add_numbers

# Terminal 3: Everything except heavy tasks
TASK_BACKEND_TYPE=celery task-backend-worker --exclude-tasks=simulate_work

# Test with Python client
python test_task_filtering.py
```

## Expected Log Output

### Worker with task filtering:
```
INFO : [2025-01-15 10:30:45]{module:worker process:1234 thread:5678 request_id:- trace_id:- span_id:-} :- Starting task backend worker - backend: celery, worker: task-worker-01
INFO : [2025-01-15 10:30:45]{module:worker process:1234 thread:5678 request_id:- trace_id:- span_id:-} :- Registering tasks with backend: celery
INFO : [2025-01-15 10:30:45]{module:worker process:1234 thread:5678 request_id:- trace_id:- span_id:-} :- Task registration completed - registered 2 tasks: add_numbers, process_data
INFO : [2025-01-15 10:30:45]{module:worker process:1234 thread:5678 request_id:- trace_id:- span_id:-} :- Skipped 3 tasks due to filtering: health_check, echo, simulate_work
INFO : [2025-01-15 10:30:45]{module:worker process:1234 thread:5678 request_id:- trace_id:- span_id:-} :- Task filter active - only allowing: add_numbers, process_data
```

## Benefits Achieved

1. **🎯 Resource Optimization** - Right-size workers per task type
2. **📈 Independent Scaling** - Scale API vs batch workers separately
3. **💰 Cost Control** - No wasted resources on unused tasks
4. **🔧 Operational Flexibility** - Deploy/restart workers independently
5. **🚀 Performance Isolation** - Heavy tasks don't block lightweight ones
6. **📊 Clear Monitoring** - Separate metrics per worker type

This gives infrastructure teams complete flexibility to deploy workers exactly as needed! 🎯