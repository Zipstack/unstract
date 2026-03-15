# Local Dev Setup: Executor Migration (Pluggable Executor System v2)

> **Branch:** `feat/execution-backend`
> **Date:** 2026-02-19

This guide covers everything needed to run and test the executor migration locally.

---

## Table of Contents

1. [Architecture Overview (Post-Migration)](#1-architecture-overview-post-migration)
2. [Prerequisites](#2-prerequisites)
3. [Service Dependency Map](#3-service-dependency-map)
4. [Step-by-Step Setup](#4-step-by-step-setup)
5. [Environment Configuration](#5-environment-configuration)
6. [Running the Executor Worker](#6-running-the-executor-worker)
7. [Port Reference](#7-port-reference)
8. [Health Check Endpoints](#8-health-check-endpoints)
9. [Debugging & Troubleshooting](#9-debugging--troubleshooting)
10. [Test Verification Checklist](#10-test-verification-checklist)

---

## 1. Architecture Overview (Post-Migration)

```
┌──────────────────────────────────────────────────────────────┐
│ CALLERS                                                       │
│                                                               │
│ Workflow Path:                                                │
│   process_file_batch → structure_tool_task                    │
│     → ExecutionDispatcher.dispatch()  [Celery]                │
│     → AsyncResult.get()                                       │
│                                                               │
│ Prompt Studio IDE:                                            │
│   Django View → PromptStudioHelper                            │
│     → ExecutionDispatcher.dispatch()  [Celery]                │
│     → AsyncResult.get()                                       │
└───────────────────────┬──────────────────────────────────────┘
                        │ Celery task: execute_extraction
                        ▼
┌──────────────────────────────────────────────────────────────┐
│ EXECUTOR WORKER (dedicated, queue: "executor")                │
│                                                               │
│ execute_extraction task                                       │
│   → ExecutionOrchestrator → ExecutorRegistry → LegacyExecutor │
│   → Returns ExecutionResult via Celery result backend         │
└──────────────────────────────────────────────────────────────┘
```

**What changed:**
- `prompt-service` Flask app is **replaced** by the executor worker (Celery)
- Structure tool Docker container is **replaced** by `structure_tool_task` (Celery task in file_processing worker)
- `PromptTool` SDK HTTP client is **replaced** by `ExecutionDispatcher` (Celery dispatch)
- **No DB schema changes** — no Django migrations needed

**What stays the same:**
- `platform-service` (port 3001) — still serves tool metadata
- `runner` (port 5002) — still needed for Classifier, Text Extractor, Translate tools
- `x2text-service` (port 3004) — still needed for text extraction
- All adapter SDKs (LLM, Embedding, VectorDB, X2Text) — used by LegacyExecutor via ExecutorToolShim
- Frontend — no changes (same REST API responses)

---

## 2. Prerequisites

### 2.1 System Requirements

| Requirement | Minimum | Notes |
|---|---|---|
| Docker + Docker Compose | v2.20+ | `docker compose version` |
| Python | 3.11+ | System or pyenv |
| uv | Latest | `pip install uv` or use the repo-local binary at `backend/venv/bin/uv` |
| Git | 2.30+ | On `feat/execution-backend` branch |
| Free RAM | 8 GB+ | Many services run concurrently |
| Free Disk | 10 GB+ | Docker images + volumes |

### 2.2 Verify Branch

```bash
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract
git branch --show-current
# Expected: feat/execution-backend
```

### 2.3 Required Docker Images

The system needs these images built:

```bash
# Build all images (from docker/ directory)
cd docker
docker compose -f docker-compose.build.yaml build

# Or build just the critical ones:
docker compose -f docker-compose.build.yaml build backend
docker compose -f docker-compose.build.yaml build platform-service
docker compose -f docker-compose.build.yaml build worker-unified   # V2 workers including executor
docker compose -f docker-compose.build.yaml build runner
docker compose -f docker-compose.build.yaml build frontend
```

> **Tip:** For faster dev builds, set `MINIMAL_BUILD=1` in docker-compose.build.yaml args.

---

## 3. Service Dependency Map

### Essential Infrastructure (must be running for ANYTHING to work)

| Service | Container | Port | Purpose |
|---|---|---|---|
| PostgreSQL (pgvector) | `unstract-db` | 5432 | Primary database |
| Redis | `unstract-redis` | 6379 | Cache + queues |
| RabbitMQ | `unstract-rabbitmq` | 5672 (AMQP), 15672 (UI) | Celery message broker |
| MinIO | `unstract-minio` | 9000 (S3), 9001 (Console) | Object storage |
| Traefik | `unstract-proxy` | 80, 8080 (Dashboard) | Reverse proxy |

### Application Services

| Service | Container | Port | Required For |
|---|---|---|---|
| Backend (Django) | `unstract-backend` | 8000 | API, auth, DB migrations |
| Platform Service | `unstract-platform-service` | 3001 | Tool metadata, adapter configs |
| X2Text Service | `unstract-x2text-service` | 3004 | Text extraction (used by executor) |
| Runner | `unstract-runner` | 5002 | Non-structure tools (Classifier, etc.) |
| Frontend | `unstract-frontend` | 3000 | Web UI |
| Flipt | `unstract-flipt` | 8082 (REST), 9005 (gRPC) | Feature flags |

### Workers (V2 Unified — `--profile workers-v2`)

| Worker | Container | Health Port | Queue(s) |
|---|---|---|---|
| **Executor** | `unstract-worker-executor-v2` | 8088 | `executor` |
| File Processing | `unstract-worker-file-processing-v2` | 8082 | `file_processing`, `api_file_processing` |
| API Deployment | `unstract-worker-api-deployment-v2` | 8090 | `celery_api_deployments` |
| Callback | `unstract-worker-callback-v2` | 8083 | `file_processing_callback`, `api_file_processing_callback` |
| General | `unstract-worker-general-v2` | 8082 | `celery` |
| Notification | `unstract-worker-notification-v2` | 8085 | `notifications`, `notifications_*` |
| Log Consumer | `unstract-worker-log-consumer-v2` | 8084 | `celery_log_task_queue` |
| Scheduler | `unstract-worker-scheduler-v2` | 8087 | `scheduler` |

### Post-Migration: REMOVED Services

| Service | Port | Replaced By |
|---|---|---|
| ~~Prompt Service~~ | ~~3003~~ | Executor Worker (LegacyExecutor inline) |
| ~~Structure Tool (Docker)~~ | N/A | `structure_tool_task` (Celery) |

---

## 4. Step-by-Step Setup

### 4.1 Start Essential Infrastructure

```bash
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract/docker

# Start infrastructure services only
docker compose -f docker-compose-dev-essentials.yaml up -d
```

Wait for all services to be healthy:
```bash
docker compose -f docker-compose-dev-essentials.yaml ps
```

### 4.2 Start Application Services

**Option A: All via Docker Compose (recommended for first-time setup)**

```bash
cd docker

# Start everything including V2 workers (with executor)
docker compose --profile workers-v2 up -d
```

**Option B: Hybrid mode (services in Docker, workers local)**

This is useful when you want to iterate on worker code without rebuilding images.

```bash
# Start only infrastructure + app services (no V2 workers)
docker compose up -d

# Then run executor worker locally (see Section 6)
```

### 4.3 Verify DB Migrations

The backend container runs migrations on startup (`--migrate` flag). Verify:

```bash
docker logs unstract-backend 2>&1 | grep -i "migration"
```

### 4.4 Create Workers .env for Local Development

If running workers outside Docker, you need a local `.env`:

```bash
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract/workers

# Copy sample and adjust for local dev
cp sample.env .env
```

Then edit `workers/.env` — change all Docker hostnames to `localhost`:

```ini
# === CRITICAL CHANGES FOR LOCAL DEV ===
DJANGO_APP_BACKEND_URL=http://localhost:8000
INTERNAL_API_BASE_URL=http://localhost:8000/internal
CELERY_BROKER_BASE_URL=amqp://localhost:5672//
DB_HOST=localhost
REDIS_HOST=localhost
CACHE_REDIS_HOST=localhost
PLATFORM_SERVICE_HOST=http://localhost
PLATFORM_SERVICE_PORT=3001
PROMPT_HOST=http://localhost
PROMPT_PORT=3003
X2TEXT_HOST=http://localhost
X2TEXT_PORT=3004
UNSTRACT_RUNNER_HOST=http://localhost
UNSTRACT_RUNNER_PORT=5002
WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS='{"provider": "minio", "credentials": {"endpoint_url": "http://localhost:9000", "key": "minio", "secret": "minio123"}}'
API_FILE_STORAGE_CREDENTIALS='{"provider": "minio", "credentials": {"endpoint_url": "http://localhost:9000", "key": "minio", "secret": "minio123"}}'
```

> **Important:** The `INTERNAL_SERVICE_API_KEY` must match what the backend expects. Default dev value: `dev-internal-key-123`.

---

## 5. Environment Configuration

### 5.1 Key Environment Variables for Executor Worker

| Variable | Default (Docker) | Local Override | Purpose |
|---|---|---|---|
| `CELERY_BROKER_BASE_URL` | `amqp://unstract-rabbitmq:5672//` | `amqp://localhost:5672//` | RabbitMQ connection |
| `CELERY_BROKER_USER` | `admin` | same | RabbitMQ user |
| `CELERY_BROKER_PASS` | `password` | same | RabbitMQ password |
| `DB_HOST` | `unstract-db` | `localhost` | PostgreSQL for result backend |
| `DB_USER` | `unstract_dev` | same | DB user |
| `DB_PASSWORD` | `unstract_pass` | same | DB password |
| `DB_NAME` | `unstract_db` | same | DB name |
| `DB_PORT` | `5432` | same | DB port |
| `REDIS_HOST` | `unstract-redis` | `localhost` | Redis for caching |
| `PLATFORM_SERVICE_HOST` | `http://unstract-platform-service` | `http://localhost` | Platform service URL |
| `PLATFORM_SERVICE_PORT` | `3001` | same | Platform service port |
| `X2TEXT_HOST` | `http://unstract-x2text-service` | `http://localhost` | X2Text service URL |
| `X2TEXT_PORT` | `3004` | same | X2Text service port |
| `INTERNAL_SERVICE_API_KEY` | `dev-internal-key-123` | same | Worker→Backend auth |
| `INTERNAL_API_BASE_URL` | `http://unstract-backend:8000/internal` | `http://localhost:8000/internal` | Backend internal API |
| `WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS` | (MinIO JSON, Docker host) | (MinIO JSON, localhost) | Shared file storage |

### 5.2 Credentials Reference (Default Dev)

| Service | Username | Password |
|---|---|---|
| PostgreSQL | `unstract_dev` | `unstract_pass` |
| RabbitMQ | `admin` | `password` |
| MinIO | `minio` | `minio123` |
| Redis | (none) | (none) |

### 5.3 Hierarchical Celery Config

Worker settings use a 3-tier hierarchy (most specific wins):

1. **Worker-specific:** `EXECUTOR_TASK_TIME_LIMIT=7200`
2. **Global Celery:** `CELERY_TASK_TIME_LIMIT=3600`
3. **Code default:** (hardcoded fallback)

---

## 6. Running the Executor Worker

### 6.1 Via Docker Compose (easiest)

```bash
cd docker

# Start just the executor worker (assumes infra is up)
docker compose --profile workers-v2 up -d worker-executor-v2

# Check logs
docker logs -f unstract-worker-executor-v2
```

### 6.2 Locally with run-worker.sh

```bash
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract/workers

# Ensure .env has local overrides (Section 4.4)
./run-worker.sh executor
```

Options:
```bash
./run-worker.sh -l DEBUG executor          # Debug logging
./run-worker.sh -c 4 executor             # 4 concurrent tasks
./run-worker.sh -P threads executor       # Thread pool instead of prefork
./run-worker.sh -d executor               # Run in background (detached)
./run-worker.sh -s                        # Show status of all workers
./run-worker.sh -k                        # Kill all workers
```

### 6.3 Locally with uv (manual)

```bash
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract/workers

# Load env
set -a && source .env && set +a

# Run executor worker
uv run celery -A worker worker \
  --queues=executor \
  --loglevel=INFO \
  --pool=prefork \
  --concurrency=2 \
  --hostname=executor-worker@%h
```

### 6.4 Verify Executor Worker is Running

```bash
# Check health endpoint
curl -s http://localhost:8088/health | python3 -m json.tool

# Check Celery registered tasks
uv run celery -A worker inspect registered \
  --destination=executor-worker@$(hostname)

# Expected task: execute_extraction
```

### 6.5 Running All V2 Workers

```bash
# Via Docker
cd docker && docker compose --profile workers-v2 up -d

# Via script (local)
cd workers && ./run-worker.sh all
```

---

## 7. Port Reference

### Infrastructure

| Service | Port | URL |
|---|---|---|
| PostgreSQL | 5432 | `psql -h localhost -U unstract_dev -d unstract_db` |
| Redis | 6379 | `redis-cli -h localhost` |
| RabbitMQ AMQP | 5672 | `amqp://admin:password@localhost:5672//` |
| RabbitMQ Management | 15672 | http://localhost:15672 (admin/password) |
| MinIO S3 API | 9000 | http://localhost:9000 |
| MinIO Console | 9001 | http://localhost:9001 (minio/minio123) |
| Qdrant | 6333 | http://localhost:6333 |
| Traefik Dashboard | 8080 | http://localhost:8080 |

### Application

| Service | Port | URL |
|---|---|---|
| Backend API | 8000 | http://localhost:8000/api/v1/ |
| Frontend | 3000 | http://frontend.unstract.localhost |
| Platform Service | 3001 | http://localhost:3001 |
| X2Text Service | 3004 | http://localhost:3004 |
| Runner | 5002 | http://localhost:5002 |
| Celery Flower (optional) | 5555 | http://localhost:5555 |

### V2 Worker Health Ports

| Worker | Internal Port | External Port (Docker) |
|---|---|---|
| API Deployment | 8090 | 8085 |
| Callback | 8083 | 8086 |
| File Processing | 8082 | 8087 |
| General | 8082 | 8088 |
| Notification | 8085 | 8089 |
| Log Consumer | 8084 | 8090 |
| Scheduler | 8087 | 8091 |
| **Executor** | **8088** | **8092** |

### Debug Ports (Docker dev mode via compose.override.yaml)

| Service | Debug Port |
|---|---|
| Backend | 5678 |
| Runner | 5679 |
| Platform Service | 5680 |
| Prompt Service | 5681 |
| File Processing Worker | 5682 |
| Callback Worker | 5683 |
| API Deployment Worker | 5684 |
| General Worker | 5685 |

---

## 8. Health Check Endpoints

Every V2 worker exposes `GET /health` on its health port:

```bash
# Executor worker
curl -s http://localhost:8088/health

# Expected response:
# {"status": "healthy", "worker_type": "executor", ...}
```

All endpoints:
```
http://localhost:8080/health  — API Deployment worker
http://localhost:8081/health  — General worker
http://localhost:8082/health  — File Processing worker
http://localhost:8083/health  — Callback worker
http://localhost:8084/health  — Log Consumer worker
http://localhost:8085/health  — Notification worker
http://localhost:8087/health  — Scheduler worker
http://localhost:8088/health  — Executor worker
```

---

## 9. Debugging & Troubleshooting

### 9.1 Common Issues

**"Connection refused" to RabbitMQ/Redis/DB**
- Check Docker containers are running: `docker ps`
- Check if using Docker hostnames vs localhost (see Section 5.1)
- Ensure ports are exposed: `docker port unstract-rabbitmq`

**Executor worker starts but tasks don't execute**
- Check queue binding: Worker must listen on `executor` queue
- Check RabbitMQ UI (http://localhost:15672) → Queues tab → look for `executor` queue
- Check task is registered: `celery -A worker inspect registered`
- Check task routing in `workers/shared/infrastructure/config/registry.py`

**"Module not found" errors in executor worker**
- Ensure `PYTHONPATH` includes the workers directory
- If running locally, `cd workers` before starting
- If using `run-worker.sh`, it sets PYTHONPATH automatically

**MinIO file access errors**
- Check `WORKFLOW_EXECUTION_FILE_STORAGE_CREDENTIALS` has correct endpoint (localhost vs Docker hostname)
- Verify MinIO bucket exists: `mc ls minio/unstract/`
- MinIO bootstrap container creates the bucket on first start

**Platform service connection errors**
- Executor needs `PLATFORM_SERVICE_HOST` and `PLATFORM_SERVICE_PORT`
- Verify platform-service is running: `curl http://localhost:3001/health`

### 9.2 Useful Debug Commands

```bash
# Check all Docker containers
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Check RabbitMQ queues
docker exec unstract-rabbitmq rabbitmqctl list_queues name messages consumers

# Check Celery worker status (from workers/ dir)
cd workers && uv run celery -A worker inspect active

# Check registered tasks
cd workers && uv run celery -A worker inspect registered

# Send a test task to executor
cd workers && uv run python -c "
from worker import app
from shared.enums.task_enums import TaskName
result = app.send_task(
    TaskName.EXECUTE_EXTRACTION,
    args=[{
        'executor_name': 'legacy',
        'operation': 'extract',
        'run_id': 'test-123',
        'execution_source': 'tool',
        'executor_params': {}
    }],
    queue='executor'
)
print(f'Task ID: {result.id}')
print(f'Result: {result.get(timeout=30)}')
"

# Monitor Celery events in real-time
cd workers && uv run celery -A worker events

# Check Postgres (Celery result backend)
docker exec -it unstract-db psql -U unstract_dev -d unstract_db -c "SELECT task_id, status FROM public.celery_taskmeta ORDER BY date_done DESC LIMIT 10;"
```

### 9.3 Log Locations

| Context | Location |
|---|---|
| Docker container | `docker logs <container-name>` |
| Local worker (foreground) | stdout/stderr |
| Local worker (detached) | `workers/<worker_type>/<worker_type>.log` |
| Backend | `docker logs unstract-backend` |

---

## 10. Test Verification Checklist

### Phase 1 Sanity (Executor Framework)

- [ ] Executor worker starts and connects to Celery broker
- [ ] Health check responds: `curl http://localhost:8088/health`
- [ ] `execute_extraction` task is registered in Celery
- [ ] No-op task dispatch round-trips successfully
- [ ] Task routing: task goes to `executor` queue, processed by executor worker

### Phase 2 Sanity (LegacyExecutor)

- [ ] `extract` operation returns `{"extracted_text": "..."}`
- [ ] `index` operation returns `{"doc_id": "..."}`
- [ ] `answer_prompt` returns `{"output": {...}, "metadata": {...}, "metrics": {...}}`
- [ ] `single_pass_extraction` returns same shape as answer_prompt
- [ ] `summarize` returns `{"data": "..."}`
- [ ] Error cases return `ExecutionResult(success=False, error="...")` not unhandled exceptions

### Phase 3 Sanity (Structure Tool as Celery Task)

- [ ] Run workflow with structure tool via new Celery path
- [ ] Compare output with Docker-based structure tool output
- [ ] Non-structure tools still work via Docker/Runner (regression check)

### Phase 4 Sanity (IDE Path)

- [ ] Open Prompt Studio IDE, create/load a project
- [ ] Run extraction on a document — result displays correctly
- [ ] Run prompt answering — output persists in DB
- [ ] Error cases display properly in IDE

### Phase 5 Sanity (Decommission)

- [ ] `docker compose up` boots cleanly — no errors from missing services
- [ ] No dangling references to prompt-service, PromptTool, PROMPT_HOST, PROMPT_PORT
- [ ] All health checks pass

### Running Unit Tests

```bash
# SDK1 tests (execution framework)
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract/unstract/sdk1
/home/harini/Documents/Workspace/unstract-poc/clean/unstract/backend/venv/bin/uv run pytest -v

# Workers tests (executor, LegacyExecutor, retrievers, etc.)
cd /home/harini/Documents/Workspace/unstract-poc/clean/unstract/workers
/home/harini/Documents/Workspace/unstract-poc/clean/unstract/backend/venv/bin/uv run pytest -v
```

---

## Quick Reference: One-Liner Setup

```bash
# From repo root:
cd docker

# 1. Build images
docker compose -f docker-compose.build.yaml build

# 2. Start everything with V2 workers
docker compose --profile workers-v2 up -d

# 3. Verify
docker ps --format "table {{.Names}}\t{{.Status}}"

# 4. Check executor health
curl -s http://localhost:8092/health  # 8092 = external Docker port for executor
```

For the automated version, use the setup check script: `scripts/check-local-setup.sh`
