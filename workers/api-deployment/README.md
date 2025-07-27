# API Deployment Worker

Lightweight Celery worker for API deployment tasks.

## Overview

This worker handles:
- `async_execute_bin_api` - API workflow execution

## Running

```bash
uv sync
celery -A worker worker --loglevel=info -Q celery_api_deployments
```

## Health Check

```bash
curl http://localhost:8080/health
```
