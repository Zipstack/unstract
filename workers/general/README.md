# General Worker

Lightweight Celery worker for general tasks and webhooks.

## Overview

This worker handles:
- `send_webhook_notification` - Webhook notifications
- `async_execute_bin_general` - General workflow execution

## Running

```bash
uv sync
celery -A worker worker --loglevel=info -Q celery
```

## Health Check

```bash
curl http://localhost:8081/health
```
