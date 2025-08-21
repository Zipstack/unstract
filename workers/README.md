# Unstract Workers

Lightweight Celery workers for distributed task processing in the Unstract platform.

## Overview

Independent, microservices-based workers that communicate with the Unstract backend via internal APIs, providing:
- **75% memory reduction** compared to Django-based workers
- **Independent scaling** and deployment
- **Better fault isolation** and resilience
- **Simplified dependencies** without Django ORM

## Workers

| Worker | Queue | Purpose |
|--------|-------|---------|
| **api-deployment** | `celery_api_deployments` | API workflow deployments and executions |
| **general** | `celery` | General tasks, webhooks, standard workflows |
| **file-processing** | `file_processing` | File processing through workflow tools |
| **callback** | `file_processing_callback` | Result aggregation and workflow finalization |

## Quick Start

### 1. Install Dependencies

```bash
cd /home/ali/projects/unstract/workers
uv sync

# Install all workers
for dir in api-deployment general file-processing callback; do
    cd $dir && uv sync && cd ..
done
```

### 2. Configuration

```bash
# Copy and configure environment
cp sample.env .env
# Edit .env with your settings

# Or use environment variables
export INTERNAL_API_BASE_URL="http://localhost:8000/internal"
export INTERNAL_SERVICE_API_KEY="internal-celery-worker-key-123"
export CELERY_BROKER_URL="redis://localhost:6379/0"
```

### 3. Run Workers

```bash
# Quick start - run all workers
./run-worker.sh all

# Or run individual workers
./run-worker.sh api           # API deployment worker
./run-worker.sh general       # General worker
./run-worker.sh file          # File processing worker
./run-worker.sh callback      # Callback worker

# With options
./run-worker.sh -l DEBUG api  # Debug logging
./run-worker.sh -d general    # Background mode
./run-worker.sh -s            # Show status
./run-worker.sh -k            # Kill all
```

## Health Monitoring

```bash
# Check worker health
curl http://localhost:8080/health  # API deployment
curl http://localhost:8081/health  # General
curl http://localhost:8082/health  # File processing
curl http://localhost:8083/health  # Callback
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed architecture decisions and design patterns.

## Operations

For deployment, monitoring, and troubleshooting, see [OPERATIONS.md](OPERATIONS.md).

## Development

### Project Structure

```
workers/
├── shared/              # Common utilities and API clients
│   ├── api_client.py   # Main internal API client
│   ├── clients/        # Modular API clients
│   ├── config.py       # Configuration management
│   └── utils/          # Helper utilities
├── api-deployment/     # API workflow deployment worker
├── general/           # General purpose worker
├── file-processing/   # File processing worker
└── callback/          # Callback aggregation worker
```

### Adding New Workers

1. Create worker directory with `pyproject.toml`
2. Implement `worker.py` and `tasks.py`
3. Add to `run-worker.sh` script
4. Create deployment configurations

### Testing

```bash
# Run tests
cd /home/ali/projects/unstract/workers
uv run pytest

# Test individual worker
cd api-deployment
uv run pytest tests/
```

## Docker Deployment

```bash
# Build all workers
VERSION=local docker compose -f docker-compose.build.yaml build \
    worker-api-deployment worker-callback worker-file-processing worker-general

# Run workers
VERSION=local docker compose --profile workers-new up -d

# Check status
docker compose --profile workers-new ps

# View logs
docker compose --profile workers-new logs -f
```

## Contributing

1. Follow the architecture principles in [ARCHITECTURE_PRINCIPLES.md](../ARCHITECTURE_PRINCIPLES.md)
2. Ensure backward compatibility with existing workers
3. Add tests for new functionality
4. Update documentation as needed

## License

AGPL-3.0 - See LICENSE file for details
