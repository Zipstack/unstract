# Unstract Workers - Complete Setup Guide

This guide provides comprehensive instructions for deploying and managing the production-ready Unstract workers system.

## Overview

The workers system consists of:
- **API Deployment Worker**: Orchestrates API workflow executions using chord pattern
- **File Processing Worker**: Processes files through runner service integration  
- **Callback Worker**: Handles completion callbacks and result aggregation
- **General Worker**: Handles general purpose tasks
- **Monitoring Stack**: Prometheus, Grafana, and Flower for observability

## Quick Start

1. **Initial Setup**
   ```bash
   cd /path/to/unstract/workers
   ./scripts/setup.sh --environment development
   ```

2. **Deploy Workers**
   ```bash
   ./scripts/deploy.sh --environment development --action deploy
   ```

3. **Monitor Status**
   ```bash
   ./scripts/monitor.sh health
   ```

## Architecture

### Workflow Execution Pattern
```
API Request → Django Backend → API Deployment Worker
                                      ↓
                              Creates File Batches
                                      ↓
                              Chord Orchestration:
                              [File Processing Tasks] → Callback
                                      ↓
                              Runner Service Integration
                                      ↓
                              Result Storage & Completion
```

### Worker Types and Responsibilities

#### API Deployment Worker (`celery_api_deployments` queue)
- **Purpose**: Orchestrates API workflow executions
- **Port**: 8080 (health checks & metrics)
- **Pattern**: Creates file batches → orchestrates chord → monitors completion
- **Key Function**: `async_execute_bin_api()` in `/workers/api-deployment/tasks.py`

#### File Processing Worker (`file_processing`, `api_file_processing` queues)  
- **Purpose**: Processes individual files through runner service
- **Port**: 8082 (health checks & metrics)
- **Pattern**: Receives file batch → calls runner service → stores results
- **Key Function**: `process_file_batch_api()` in `/workers/file_processing/tasks.py`

#### Callback Worker (`file_processing_callback`, `api_file_processing_callback` queues)
- **Purpose**: Aggregates results and completes workflow execution
- **Port**: 8083 (health checks & metrics)  
- **Pattern**: Receives chord results → updates execution status → notifies completion
- **Key Function**: `process_batch_callback_api()` in `/workers/callback/tasks.py`

#### General Worker (`celery` queue)
- **Purpose**: Handles general background tasks
- **Port**: 8081 (health checks & metrics)
- **Pattern**: Standard Celery task processing

## Deployment Options

### Development Environment

```bash
# Full setup with monitoring
./scripts/deploy.sh --environment development --action deploy

# Deploy specific workers
./scripts/deploy.sh --environment development --workers api --action deploy

# Enable monitoring services
docker-compose -f docker/docker-compose.workers.yml --profile monitoring up -d
```

### Production Environment

1. **Update Configuration**
   ```bash
   # Edit production environment file
   nano docker/env/production.env
   
   # Update passwords, API keys, and hostnames
   # Example: Change CHANGE_ME_PASSWORD to actual secure passwords
   ```

2. **Deploy with Production Settings**
   ```bash
   ./scripts/deploy.sh --environment production --action deploy
   ```

3. **Enable Production Monitoring**
   ```bash
   # Start monitoring stack
   docker-compose -f docker/docker-compose.workers.yml --profile monitoring up -d
   ```

## Management Commands

### Deployment Management
```bash
# Deploy all workers
./scripts/deploy.sh --action deploy

# Stop workers
./scripts/deploy.sh --action stop

# Restart workers  
./scripts/deploy.sh --action restart

# Check status
./scripts/deploy.sh --action status

# View logs
./scripts/deploy.sh --action logs

# Scale workers
./scripts/deploy.sh --action scale --workers api
```

### Health Monitoring
```bash
# Check health status
./scripts/monitor.sh health

# Continuous monitoring
./scripts/monitor.sh --continuous --interval 15 health

# Show metrics
./scripts/monitor.sh metrics

# Check resource usage
./scripts/monitor.sh resources

# Generate comprehensive report
./scripts/monitor.sh report
```

### Troubleshooting
```bash
# Run full diagnostics
./scripts/troubleshoot.sh diagnose

# Check specific issues
./scripts/troubleshoot.sh network
./scripts/troubleshoot.sh dependencies
./scripts/troubleshoot.sh configuration

# Auto-fix common issues
./scripts/troubleshoot.sh --fix cleanup

# Reset workers (rebuild)
./scripts/troubleshoot.sh reset
```

## Configuration Files

### Environment Configuration
- **Development**: `docker/env/development.env`
- **Production**: `docker/env/production.env`

Key configuration sections:
```bash
# Core API Configuration
INTERNAL_SERVICE_API_KEY=your-api-key
DJANGO_APP_BACKEND_URL=http://backend:8000
CELERY_BROKER_URL=amqp://user:pass@rabbitmq:5672//

# Runner Service Integration  
UNSTRACT_RUNNER_HOST=http://runner
UNSTRACT_RUNNER_PORT=5002
UNSTRACT_RUNNER_API_TIMEOUT=120

# Worker Performance Tuning
MAX_CONCURRENT_TASKS=10
CELERY_WORKER_PREFETCH_MULTIPLIER=1
CELERY_WORKER_MAX_TASKS_PER_CHILD=500
```

### Docker Compose Configuration
- **Main File**: `docker/docker-compose.workers.yml`
- **Monitoring Profile**: Enable with `--profile monitoring`

### Prometheus Configuration
- **File**: `docker/monitoring/prometheus.yml`
- **Scrapes**: All worker health and metrics endpoints
- **Retention**: 15 days

## Monitoring and Observability

### Access Points
- **Flower (Celery Monitoring)**: http://localhost:5555
- **Prometheus**: http://localhost:9090  
- **Grafana**: http://localhost:3001
- **Worker Health Checks**: 
  - API Deployment: http://localhost:8080/health
  - General: http://localhost:8081/health
  - File Processing: http://localhost:8082/health
  - Callback: http://localhost:8083/health

### Metrics Available
- Worker health status
- Task execution rates
- Error rates and types
- Resource usage (CPU, Memory)
- Queue lengths and processing times
- Runner service response times

### Log Analysis
```bash
# View worker logs
./scripts/deploy.sh --action logs

# Analyze logs for errors
./scripts/troubleshoot.sh logs

# Container-specific logs
docker logs unstract-worker-api-deployment
docker logs unstract-worker-file-processing
docker logs unstract-worker-callback
```

## Security Configuration

### Production Security Checklist
- [ ] Update all `CHANGE_ME` values in production.env
- [ ] Use secure passwords for RabbitMQ, PostgreSQL, monitoring
- [ ] Enable SSL/TLS for external communications
- [ ] Restrict network access to monitoring ports
- [ ] Use proper API keys for internal service communication
- [ ] Enable audit logging for sensitive operations

### Network Security
```bash
# Create isolated network
docker network create unstract_network

# Restrict external access
# Only expose necessary ports (5555, 9090, 3001 for monitoring)
```

## Performance Tuning

### Worker Scaling
```bash
# Scale API deployment workers
./scripts/deploy.sh --action scale --workers api
# Enter desired count when prompted

# Scale general workers  
./scripts/deploy.sh --action scale --workers general
```

### Resource Limits
Configured in `docker-compose.workers.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 512M
      cpus: '1.0'
    reservations:
      memory: 256M
      cpus: '0.5'
```

### Celery Optimization
Key settings in environment files:
```bash
# Task acknowledgment
CELERY_TASK_ACKS_LATE=true

# Prefetch control
CELERY_WORKER_PREFETCH_MULTIPLIER=1

# Worker recycling
CELERY_WORKER_MAX_TASKS_PER_CHILD=500
```

## Troubleshooting Common Issues

### Worker Not Starting
```bash
# Check container status
./scripts/troubleshoot.sh diagnose

# Check logs for errors
docker logs unstract-worker-api-deployment

# Verify configuration
./scripts/troubleshoot.sh configuration
```

### High Memory Usage
```bash
# Check resource usage
./scripts/monitor.sh resources

# Tune worker limits
# Edit CELERY_WORKER_MAX_TASKS_PER_CHILD in env file
```

### Runner Service Connection Issues
```bash
# Check runner service availability
curl http://localhost:5002/health

# Verify environment variables
grep UNSTRACT_RUNNER docker/env/development.env

# Check network connectivity
./scripts/troubleshoot.sh network
```

### Organization Context Issues
- Ensure `INTERNAL_SERVICE_API_KEY` matches backend configuration
- Verify organization resolution in `backend/utils/organization_utils.py`
- Check fallback organization resolution in workflow helper

## Migration from Previous Workers

If migrating from Django-based heavy workers:

1. **Stop Old Workers**
   ```bash
   # Stop any running Django celery workers
   pkill -f "celery.*worker"
   ```

2. **Deploy New Workers**
   ```bash
   ./scripts/setup.sh --environment development
   ./scripts/deploy.sh --action deploy
   ```

3. **Verify Task Routing**
   - Ensure queue routing in `config/queue_routing.py` matches new workers
   - Test API workflow execution end-to-end
   - Monitor logs for proper task distribution

## Production Deployment Checklist

- [ ] Updated production environment file with secure values
- [ ] Docker network created and properly configured
- [ ] Database and message broker accessible
- [ ] Runner service deployed and accessible
- [ ] Worker images built and tested
- [ ] Monitoring stack deployed and configured
- [ ] Health checks passing for all workers
- [ ] Test workflow execution end-to-end
- [ ] Log aggregation configured
- [ ] Backup and recovery procedures in place
- [ ] Alerting rules configured in Prometheus/Grafana

## Support and Maintenance

### Regular Maintenance Tasks
```bash
# Weekly health check
./scripts/monitor.sh report

# Monthly cleanup
./scripts/troubleshoot.sh --fix cleanup

# Quarterly performance review
./scripts/monitor.sh --continuous performance
```

### Log Rotation
Configure log rotation for worker containers:
```bash
# Docker daemon configuration
echo '{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}' > /etc/docker/daemon.json
```

### Backup Considerations
- Environment configuration files
- Prometheus metrics data (optional)
- Worker deployment scripts and configurations

For additional support, refer to:
- Worker architecture documentation in `ARCHITECTURE.md`
- Individual worker README files
- Troubleshooting script help: `./scripts/troubleshoot.sh --help`
