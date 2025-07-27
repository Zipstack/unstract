# Callback Worker

Lightweight Celery worker for result callbacks and aggregation.

## Overview

This worker handles:
- `process_batch_callback` - Result aggregation
- `process_batch_callback_api` - API result callbacks

## Running

```bash
uv sync
celery -A worker worker --loglevel=info -Q file_processing_callback
```

## Health Check

```bash
curl http://localhost:8083/health
```
