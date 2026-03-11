# Executor Worker

Celery worker that handles LLM extraction, indexing, and prompt execution for the Unstract platform.

## How It Works

```text
Browser → Django Backend → RabbitMQ → Executor Worker → Callback → WebSocket → Browser
```

1. User clicks "Run" in Prompt Studio IDE → Backend dispatches task to `celery_executor_legacy` queue
2. Executor worker picks up task, runs LLM extraction
3. Result triggers callback on `prompt_studio_callback` queue
4. Callback worker saves results to DB and pushes via Socket.IO
5. Browser receives result in real-time

## Services Involved

| Service | Purpose |
|---------|---------|
| `worker-executor-v2` | Runs LLM extraction, indexing, prompts |
| `worker-prompt-studio-callback` | Post-execution ORM writes + Socket.IO events |
| `backend` | Django REST API + Socket.IO |
| `platform-service` | Adapter credential management |
| `prompt-service` | Prompt template service |

## Configuration

The executor worker starts automatically with `./run-platform.sh` — no extra configuration needed.

Key environment variables (in `docker/sample.env` and `workers/sample.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `WORKER_EXECUTOR_CONCURRENCY` | `2` | Number of concurrent executor processes |
| `WORKER_EXECUTOR_POOL` | `prefork` | Celery pool type |
| `EXECUTOR_TASK_TIME_LIMIT` | `3600` | Hard timeout per task (seconds) |
| `EXECUTOR_TASK_SOFT_TIME_LIMIT` | `3300` | Soft timeout per task (seconds) |
| `EXECUTOR_RESULT_TIMEOUT` | `3600` | How long callers wait for results |
| `EXECUTOR_AUTOSCALE` | `2,1` | Max,min worker autoscale |

## Queue

Listens on: `celery_executor_legacy`

Configurable via `CELERY_QUEUES_EXECUTOR` environment variable.

## Docker

Defined in `docker/docker-compose.yaml` as `worker-executor-v2`. Uses the unified worker image (`unstract/worker-unified`) with `executor` command.

## Local Development

```bash
cd workers
cp sample.env .env
# Edit .env: change Docker hostnames to localhost
./run-worker.sh executor
```
