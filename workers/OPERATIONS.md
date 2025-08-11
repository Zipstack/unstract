# Unstract Workers - Operations Guide

This guide consolidates deployment, monitoring, and troubleshooting information for Unstract workers.

## Deployment

### Development Setup

```bash
# Quick setup for development
cd /home/ali/projects/unstract/workers
./scripts/setup.sh --environment development

# Install dependencies
uv sync
for dir in api-deployment general file-processing callback; do
    cd $dir && uv sync && cd ..
done
```

### Production Deployment

#### Docker Deployment

```bash
# Build images
VERSION=local docker compose -f docker-compose.build.yaml build \
    worker-api-deployment worker-callback worker-file-processing worker-general

# Run workers
VERSION=local docker compose --profile workers-new up -d
```

#### Kubernetes Deployment

```yaml
# See docker/kubernetes/ for complete manifests
kubectl apply -f docker/kubernetes/workers/
```

### Environment Configuration

Copy `sample.env` to `.env` and configure:

**Required:**
- `INTERNAL_API_BASE_URL`: Backend internal API URL
- `INTERNAL_SERVICE_API_KEY`: Authentication key
- `CELERY_BROKER_URL`: Message broker URL
- `CELERY_RESULT_BACKEND`: Result storage backend

**Worker-Specific:**
- `[WORKER]_MAX_CONCURRENT_TASKS`: Concurrency limits
- `[WORKER]_HEALTH_PORT`: Health check ports
- `[WORKER]_QUEUE`: Queue names

## Monitoring

### Health Checks

```bash
# Check all workers health
./scripts/monitor.sh health

# Individual worker health
curl http://localhost:8080/health  # API deployment worker
curl http://localhost:8081/health  # General worker
curl http://localhost:8082/health  # File processing worker
curl http://localhost:8083/health  # Callback worker
```

### Metrics (Prometheus)

Workers expose metrics on their health ports at `/metrics`:
- Task execution counts
- Processing times
- Queue depths
- Error rates

### Logging

Workers use structured logging with configurable levels:
```bash
export LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
export LOG_FORMAT=json  # json or simple
```

### Flower Dashboard

```bash
# Start Flower for task monitoring
celery -A backend flower --port=5555
# Access at http://localhost:5555
```

## Troubleshooting

### Common Issues

#### Workers Not Processing Tasks

1. **Check connectivity:**
   ```bash
   # Test Redis/RabbitMQ connection
   redis-cli ping
   rabbitmqctl status
   ```

2. **Verify API access:**
   ```bash
   curl -H "X-API-Key: $INTERNAL_SERVICE_API_KEY" \
        $INTERNAL_API_BASE_URL/v1/health/
   ```

3. **Check worker logs:**
   ```bash
   docker logs unstract-worker-api-deployment-new
   # Or for local development
   tail -f logs/api-deployment-worker.log
   ```

#### Memory Issues

- Adjust `CELERY_WORKER_MAX_TASKS_PER_CHILD` (default: 1000)
- Configure `[WORKER]_MAX_CONCURRENT_TASKS` based on available memory
- Enable memory profiling with `ENABLE_MEMORY_PROFILING=true`

#### Task Timeouts

- Increase `CELERY_TASK_TIMEOUT` (default: 300s)
- Adjust `CELERY_TASK_SOFT_TIMEOUT` (default: 270s)
- Configure worker-specific timeouts in environment

#### Circuit Breaker Trips

When API calls fail repeatedly:
- Check `CIRCUIT_BREAKER_FAILURE_THRESHOLD` (default: 5)
- Adjust `CIRCUIT_BREAKER_RECOVERY_TIMEOUT` (default: 60s)
- Review backend API logs for errors

### Debug Mode

Enable detailed debugging:
```bash
export DEBUG=true
export LOG_LEVEL=DEBUG
export CELERY_TASK_ALWAYS_EAGER=true  # Run tasks synchronously
```

### Performance Tuning

#### Concurrency Settings
```bash
# Per worker type
API_DEPLOYMENT_MAX_CONCURRENT_TASKS=5
GENERAL_MAX_CONCURRENT_TASKS=10
FILE_PROCESSING_MAX_CONCURRENT_TASKS=4
CALLBACK_MAX_CONCURRENT_TASKS=3
```

#### Autoscaling
```bash
# Format: max,min
API_DEPLOYMENT_AUTOSCALE=4,1
GENERAL_AUTOSCALE=6,2
FILE_PROCESSING_AUTOSCALE=8,2
CALLBACK_AUTOSCALE=4,1
```

#### Connection Pooling
```bash
CONNECTION_POOL_SIZE=10
CONNECTION_POOL_MAX_OVERFLOW=20
```

## Maintenance

### Log Rotation

Configure log rotation in production:
```bash
# /etc/logrotate.d/unstract-workers
/var/log/unstract/workers/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
```

### Backup and Recovery

- Task results are stored in Redis/PostgreSQL
- Configure `EXECUTION_RESULT_TTL_SECONDS` for retention
- Enable `ENABLE_TASK_BACKUP=true` for critical workflows

### Upgrading Workers

1. **Rolling update (recommended):**
   ```bash
   ./scripts/deploy.sh --environment production --action rolling-update
   ```

2. **Blue-green deployment:**
   ```bash
   # Deploy new version
   ./scripts/deploy.sh --environment production --action deploy --version new
   # Switch traffic
   ./scripts/deploy.sh --environment production --action switch --to new
   # Remove old version
   ./scripts/deploy.sh --environment production --action cleanup --version old
   ```

## Support

- **Documentation**: See README.md for architecture details
- **Issues**: Report at https://github.com/unstract/unstract/issues
- **Logs**: Check `/var/log/unstract/workers/` or Docker logs
- **Metrics**: Access Prometheus at `:9090` and Grafana at `:3000`
