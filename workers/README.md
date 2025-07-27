# Unstract Workers

Lightweight Celery workers for distributed task processing in the Unstract platform.

## Architecture

This package provides independent, lightweight Celery workers that communicate with the Unstract backend via internal APIs instead of direct database access. This architecture enables:

- **Independent scaling** of different worker types
- **Reduced resource usage** (75% memory reduction vs Django workers)
- **Simplified deployment** with minimal dependencies
- **Better fault isolation** and resilience

## Workers

### Core Workers
- **`api-deployment/`** - Handles API workflow deployments and executions
- **`general/`** - Manages general tasks including webhooks and standard workflows
- **`file-processing/`** - Processes files through workflow tools using hybrid API approach
- **`callback/`** - Aggregates results and finalizes workflow executions

### Shared Infrastructure
- **`shared/`** - Common utilities for API clients, logging, health checks, and configuration

## Quick Start

### 1. Install Dependencies

```bash
# Install shared utilities
cd /home/ali/projects/unstract/workers
uv sync

# Install individual workers
cd api-deployment && uv sync && cd ..
cd general && uv sync && cd ..
cd file-processing && uv sync && cd ..
cd callback && uv sync && cd ..
```

### 2. Configuration

#### Using Environment File (Recommended)

```bash
# Copy sample environment file
cp sample.env .env

# Edit .env file with your configuration
nano .env
```

#### Manual Environment Variables

```bash
# Backend Configuration
export INTERNAL_API_BASE_URL="http://localhost:8000/internal"
export INTERNAL_SERVICE_API_KEY="internal-celery-worker-key-123"

# Celery Configuration (matches backend patterns)
export CELERY_BROKER_BASE_URL="redis://localhost:6379//"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"

# For RabbitMQ (production)
# export CELERY_BROKER_BASE_URL="amqp://localhost:5672//"
# export CELERY_BROKER_USER="admin"
# export CELERY_BROKER_PASS="password"

# Optional Configuration
export LOG_LEVEL="INFO"
export WORKER_CONCURRENCY="4"
```

### 3. Start Backend Services

Ensure these services are running:

```bash
# Start Django backend (in another terminal)
cd /home/ali/projects/unstract/backend
source .venv/bin/activate
uv run manage.py runserver localhost:8000

# Start Redis (if not running)
redis-server

# Start RabbitMQ (if using AMQP)
sudo systemctl start rabbitmq-server
```

## Running Workers

### Method 1: Using Convenience Script (Recommended)

The `run-worker.sh` script provides an easy way to run workers with proper configuration:

```bash
# Run single workers
./run-worker.sh api           # API deployment worker
./run-worker.sh general       # General worker  
./run-worker.sh file          # File processing worker
./run-worker.sh callback      # Callback worker
./run-worker.sh all           # All workers in background

# With options
./run-worker.sh -l DEBUG api                    # Debug logging
./run-worker.sh -d general                      # Run in background
./run-worker.sh -c 4 file                       # Custom concurrency
./run-worker.sh -e production.env all           # Custom env file

# Worker management
./run-worker.sh -s                              # Show worker status
./run-worker.sh -k                              # Kill all workers

# Worker naming and scaling
./run-worker.sh -n api-01 api                   # Custom worker name  
./run-worker.sh -n api-02 api                   # Second API worker instance
```

### Method 2: Individual Workers (Manual)

Each worker runs in its own process with specific queues:

```bash
# Terminal 1: API Deployment Worker
cd /home/ali/projects/unstract/workers/api-deployment
uv run celery -A worker worker --loglevel=info -Q celery_api_deployments --autoscale 4,1

# Terminal 2: General Worker
cd /home/ali/projects/unstract/workers/general
uv run celery -A worker worker --loglevel=info -Q celery --autoscale 6,2

# Terminal 3: File Processing Worker
cd /home/ali/projects/unstract/workers/file_processing
uv run celery -A worker worker --pool=threads --loglevel=info -Q file_processing,api_file_processing --concurrency 4

# Terminal 4: Callback Worker
cd /home/ali/projects/unstract/workers/callback
uv run celery -A worker worker --loglevel=info -Q file_processing_callback,api_file_processing_callback --autoscale 4,1
```

### Method 3: Using Python Directly (Alternative)

```bash
# API Deployment Worker
cd /home/ali/projects/unstract/workers/api-deployment
uv run celery -A worker worker --loglevel=info -Q celery_api_deployments

# General Worker
cd /home/ali/projects/unstract/workers/general
uv run celery -A worker worker --loglevel=info -Q celery

# File Processing Worker
cd /home/ali/projects/unstract/workers/file-processing
uv run celery -A worker worker --pool=threads --loglevel=info -Q file_processing --concurrency 4

# Callback Worker
cd /home/ali/projects/unstract/workers/callback
uv run celery -A worker worker --loglevel=info -Q file_processing_callback
```

### Method 3: Development Mode (Single Queue for Testing)

For testing individual workers:

```bash
# Test API deployment worker only
cd /home/ali/projects/unstract/workers/api-deployment
uv run celery -A worker worker --loglevel=debug -Q celery_api_deployments --concurrency 1

# Test with specific task
uv run celery -A worker worker --loglevel=debug -Q celery_api_deployments --pool=solo
```

## Health Monitoring

Each worker provides health endpoints (when health server is enabled):

```bash
# Check all worker health
curl http://localhost:8080/health  # API Deployment
curl http://localhost:8081/health  # General
curl http://localhost:8082/health  # File Processing  
curl http://localhost:8083/health  # Callback

# Expected response
{
  "status": "healthy",
  "worker": "api-deployment",
  "uptime": "00:05:23",
  "active_tasks": 2,
  "processed_tasks": 145
}
```

## Monitoring & Debugging

### Celery Flower (Task Monitoring)

```bash
# Start Flower for task monitoring
cd /home/ali/projects/unstract/workers
uv run celery -A api-deployment.worker flower --port=5555

# Access at http://localhost:5555
```

### Logs

Workers use structured JSON logging:

```bash
# View logs with specific log level
LOG_LEVEL=DEBUG uv run celery -A worker worker --loglevel=debug

# Filter logs for specific worker
tail -f /var/log/unstract/workers/api-deployment.log | jq '.message'
```

### Queue Status

```bash
# Check queue lengths (Redis)
redis-cli llen celery
redis-cli llen celery_api_deployments
redis-cli llen file_processing

# Check active workers
celery -A api-deployment.worker inspect active
```

## Production Deployment

### Using Supervisor (Recommended)

Create supervisor configs:

```ini
# /etc/supervisor/conf.d/unstract-worker-api.conf
[program:unstract-worker-api]
command=/home/ali/projects/unstract/workers/api-deployment/.venv/bin/celery -A worker worker --loglevel=info -Q celery_api_deployments --autoscale 4,1
directory=/home/ali/projects/unstract/workers/api-deployment
user=unstract
autostart=true
autorestart=true
stopwaitsecs=10
killasgroup=true
priority=998
```

```bash
# Start all workers
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start unstract-worker-api
sudo supervisorctl start unstract-worker-general
sudo supervisorctl start unstract-worker-file
sudo supervisorctl start unstract-worker-callback
```

### Using Docker

```bash
# Build worker images
cd /home/ali/projects/unstract
docker build -f workers/docker/api-deployment.Dockerfile -t unstract-worker-api .
docker build -f workers/docker/general.Dockerfile -t unstract-worker-general .

# Run with docker-compose
cd workers
docker-compose -f docker/docker-compose.workers.yml up -d
```

### Using systemd

```ini
# /etc/systemd/system/unstract-worker-api.service
[Unit]
Description=Unstract API Deployment Worker
After=network.target redis.service

[Service]
Type=exec
User=unstract
WorkingDirectory=/home/ali/projects/unstract/workers/api-deployment
Environment=CELERY_BROKER_URL=redis://localhost:6379/0
Environment=INTERNAL_API_BASE_URL=http://localhost:8000/internal
ExecStart=/home/ali/projects/unstract/workers/api-deployment/.venv/bin/celery -A worker worker --loglevel=info -Q celery_api_deployments --autoscale 4,1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start services
sudo systemctl enable unstract-worker-api
sudo systemctl start unstract-worker-api
sudo systemctl status unstract-worker-api
```

## Troubleshooting

### Common Issues

1. **Import Errors**
   ```bash
   # Ensure shared package is installed
   cd /home/ali/projects/unstract/workers
   uv sync
   
   # Check Python path
   cd api-deployment
   uv run python -c "import shared; print('OK')"
   ```

2. **Connection Refused**
   ```bash
   # Check backend is running
   curl http://localhost:8000/internal/v1/health/
   
   # Check Redis connection
   redis-cli ping
   ```

3. **Authentication Failed**
   ```bash
   # Verify API key matches Django settings
   curl -H "Authorization: Bearer internal-celery-worker-key-123" \
        http://localhost:8000/internal/v1/health/
   ```

4. **High Memory Usage**
   ```bash
   # Use thread pool for file processing
   celery -A worker worker --pool=threads --concurrency 2
   
   # Monitor memory
   ps aux | grep celery
   ```

### Debug Mode

```bash
# Run with maximum verbosity
LOG_LEVEL=DEBUG celery -A worker worker --loglevel=debug --pool=solo -Q test_queue

# Test specific task
uv run python -c "
from tasks import async_execute_bin_api
result = async_execute_bin_api.delay('test', 'workflow_id', 'exec_id', [])
print(result.get())
"
```

## Development

### Adding New Workers

1. Create new worker directory:
   ```bash
   mkdir /home/ali/projects/unstract/workers/my-worker
   cd my-worker
   ```

2. Create `pyproject.toml`:
   ```toml
   [project]
   name = "unstract-worker-my-worker"
   dependencies = ["unstract-workers"]
   
   [tool.uv.sources]
   unstract-workers = { path = "../", editable = true }
   ```

3. Create `worker.py` and `tasks.py`
4. Add to main pyproject.toml
5. Create deployment configs

### Testing

```bash
# Test shared utilities
cd /home/ali/projects/unstract/workers
uv run pytest shared/

# Test individual worker
cd api-deployment
uv run pytest tests/

# Integration tests
uv run pytest tests/integration/
```

This documentation provides comprehensive instructions for running, monitoring, and deploying the lightweight Celery workers in any environment.
