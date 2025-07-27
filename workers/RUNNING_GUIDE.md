# 🚀 Quick Start Guide: Running Unstract Workers

## Prerequisites ✅

1. **Backend running** on `http://localhost:8000`
2. **Redis running** on `localhost:6379` 
3. **Workers installed** with UV package management

## Step-by-Step Setup

### 1. Install All Workers

```bash
# From project root
cd /home/ali/projects/unstract

# Option A: Install all workers via main pyproject.toml
uv sync --group workers

# Option B: Install workers individually  
cd workers
uv sync                    # Shared utilities
cd api-deployment && uv sync && cd ..
cd general && uv sync && cd ..
cd file-processing && uv sync && cd ..
cd callback && uv sync && cd ..
```

### 2. Set Environment Variables

```bash
# Required for all workers
export INTERNAL_API_BASE_URL="http://localhost:8000/internal"
export INTERNAL_SERVICE_API_KEY="internal-celery-worker-key-123"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"

# Optional
export LOG_LEVEL="INFO"
```

### 3. Start Backend Services

```bash
# Terminal 1: Start Django backend
cd /home/ali/projects/unstract/backend
source .venv/bin/activate
uv run manage.py runserver localhost:8000

# Terminal 2: Start Redis (if not running)
redis-server

# Verify backend is accessible
curl http://localhost:8000/internal/v1/health/
```

### 4. Run Workers (Choose One Method)

#### Method A: UV Run (Recommended)

```bash
# Terminal 3: API Deployment Worker
cd /home/ali/projects/unstract/workers/api-deployment
uv run celery -A worker worker --loglevel=info -Q celery_api_deployments

# Terminal 4: General Worker
cd /home/ali/projects/unstract/workers/general
uv run celery -A worker worker --loglevel=info -Q celery

# Terminal 5: File Processing Worker
cd /home/ali/projects/unstract/workers/file-processing
uv run celery -A worker worker --pool=threads --loglevel=info -Q file_processing --concurrency 4

# Terminal 6: Callback Worker
cd /home/ali/projects/unstract/workers/callback
uv run celery -A worker worker --loglevel=info -Q file_processing_callback
```

#### Method B: Virtual Environment

```bash
# Terminal 3: API Deployment Worker
cd /home/ali/projects/unstract/workers/api-deployment
source .venv/bin/activate
celery -A worker worker --loglevel=info -Q celery_api_deployments --autoscale 4,1

# Terminal 4: General Worker
cd /home/ali/projects/unstract/workers/general
source .venv/bin/activate
celery -A worker worker --loglevel=info -Q celery --autoscale 4,1

# And so on...
```

## Verification ✅

### Check Worker Status

```bash
# Check if workers are receiving tasks
celery -A api-deployment.worker inspect active
celery -A general.worker inspect registered

# Check queue lengths
redis-cli llen celery
redis-cli llen celery_api_deployments
redis-cli llen file_processing
redis-cli llen file_processing_callback
```

### Health Checks

```bash
# Check worker health endpoints (if enabled)
curl http://localhost:8080/health  # API Deployment
curl http://localhost:8081/health  # General
curl http://localhost:8082/health  # File Processing
curl http://localhost:8083/health  # Callback
```

### Test Task Execution

```bash
# From Django admin or shell
cd /home/ali/projects/unstract/backend
uv run manage.py shell

# Test sending a task
from celery import Celery
app = Celery('test')
app.config_from_object('django.conf:settings', namespace='CELERY')
result = app.send_task('async_execute_bin_api', args=['test', 'workflow', 'exec', []])
print(result.get())
```

## Monitoring 📊

### Celery Flower

```bash
# Start Flower for web monitoring
cd /home/ali/projects/unstract/workers
uv run celery -A api-deployment.worker flower --port=5555

# Access at: http://localhost:5555
```

### Logs

```bash
# View worker logs
LOG_LEVEL=DEBUG uv run celery -A worker worker --loglevel=debug

# Monitor queue activity
watch redis-cli llen celery
```

## Troubleshooting 🔧

### Common Issues

1. **"ImportError: No module named shared"**
   ```bash
   cd /home/ali/projects/unstract/workers
   uv sync  # Ensure shared package is installed
   ```

2. **"Connection refused to localhost:8000"**
   ```bash
   # Check Django backend is running
   curl http://localhost:8000/internal/v1/health/
   ```

3. **"Authentication failed"**
   ```bash
   # Check API key matches backend settings
   grep INTERNAL_SERVICE_API_KEY /home/ali/projects/unstract/backend/.env
   ```

4. **"No such queue: celery_api_deployments"**
   ```bash
   # Check queue routing in Django settings
   grep TASK_ROUTES /home/ali/projects/unstract/backend/backend/settings/base.py
   ```

### Debug Mode

```bash
# Run single worker with full debug output
cd /home/ali/projects/unstract/workers/api-deployment
LOG_LEVEL=DEBUG uv run celery -A worker worker --loglevel=debug --pool=solo -Q celery_api_deployments
```

## Quick Commands Reference

```bash
# Install everything from root
cd /home/ali/projects/unstract && uv sync --group workers

# Start all services (different terminals)
cd backend && uv run manage.py runserver localhost:8000
cd workers/api-deployment && uv run celery -A worker worker --loglevel=info -Q celery_api_deployments  
cd workers/general && uv run celery -A worker worker --loglevel=info -Q celery
cd workers/file-processing && uv run celery -A worker worker --pool=threads --loglevel=info -Q file_processing --concurrency 4
cd workers/callback && uv run celery -A worker worker --loglevel=info -Q file_processing_callback

# Monitor
uv run celery -A api-deployment.worker flower --port=5555
```

🎉 **You're ready to run lightweight Celery workers!**
