# CLAUDE.md - Unstract Development Guide

## Project Overview

Unstract is an open-source platform for automating document-based workflows using LLMs. It extracts structured data from unstructured documents (PDFs, images, Word docs, etc.) with near 100% accuracy. The platform provides Prompt Studio for schema definition, API deployments, ETL pipelines, and MCP server integrations.

## Repository Structure

```
unstract/
├── backend/              # Django REST API backend (main application server)
├── frontend/             # React SPA (Ant Design UI)
├── platform-service/     # Flask microservice for SDK/tool interactions
├── prompt-service/       # Flask microservice for Prompt Studio operations
├── runner/               # Flask microservice for tool Docker lifecycle
├── workers/              # Celery workers (unified worker architecture)
├── x2text-service/       # Flask microservice for text extraction
├── tool-sidecar/         # Sidecar container for tools
├── tools/                # Built-in tools (classifier, structure, text_extractor)
├── unstract/             # Core Python libraries (shared packages)
│   ├── connectors/       # Connector abstractions (S3, GCS, Dropbox, etc.)
│   ├── core/             # Shared utilities and base classes
│   ├── filesystem/       # Filesystem abstractions
│   ├── flags/            # Feature flag client (Flipt)
│   ├── sdk1/             # SDK v1 for tool development (LLM, embedding, vector DB)
│   ├── tool-registry/    # Tool discovery and registry
│   ├── tool-sandbox/     # Tool sandboxing utilities
│   └── workflow-execution/ # Workflow execution engine
├── docker/               # Docker Compose configs and Dockerfiles
├── pyproject.toml        # Root project config (ruff, mypy, pytest settings)
├── tox.ini               # Test runner configuration
├── run-platform.sh       # Quick start script (Docker-based deployment)
└── dev-env-cli.sh        # Development environment setup CLI
```

## Tech Stack

| Component | Technology |
|---|---|
| Backend API | Django 4.2 + Django REST Framework 3.14 |
| Frontend | React 18 + Ant Design 5 + Zustand (state) |
| Microservices | Flask 3.x + Peewee ORM (platform/prompt/x2text) |
| Runner | Flask 3.x + Docker SDK |
| Workers | Celery 5.x (RabbitMQ broker) |
| Database | PostgreSQL 15 (pgvector extension) |
| Cache/Broker | Redis 7.x + RabbitMQ 4.x |
| Object Storage | MinIO (S3-compatible) |
| Feature Flags | Flipt |
| Reverse Proxy | Traefik v3 |
| Vector DB | Qdrant (default), also supports Pinecone, Weaviate, Milvus |
| Package Manager | uv (Python), npm (frontend) |
| Python Version | 3.12 (required, >=3.12 <3.13) |
| Node Version | >=16.0.0 <20 |

## Backend (Django)

### Project Structure

The backend is a Django project at `backend/` with settings in `backend/backend/settings/`:

- `base.py` - Base settings (shared across environments)
- `dev.py` - Development overrides
- `test.py` - Test environment settings

Settings module is controlled by `DJANGO_SETTINGS_MODULE` env var (default: `backend.settings.dev`).

### Django Apps

Core apps (all use the `_v2` suffix for the current version):

| App | Purpose |
|---|---|
| `account_v2` | User/organization management, auth |
| `account_usage` | Usage tracking |
| `adapter_processor_v2` | LLM/embedding/vector DB adapter management |
| `api_v2` | API deployment endpoints |
| `configuration` | Platform configuration |
| `connector_v2` | Data source/destination connectors |
| `connector_auth_v2` | OAuth flows for connectors |
| `connector_processor` | Connector processing logic |
| `feature_flag` | Feature flag integration (Flipt) |
| `file_management` | File upload/download handling |
| `logs_helper` | Log retrieval endpoints |
| `notification_v2` | Notification system |
| `pipeline_v2` | ETL pipeline management |
| `platform_settings_v2` | Platform-level settings |
| `prompt_studio.*` | Prompt Studio sub-apps (core, profiles, registry, documents, outputs, indexes) |
| `tags` | Tagging system |
| `tenant_account_v2` | Tenant/org account management |
| `tool_instance_v2` | Tool instance configuration |
| `usage_v2` | Usage metrics |
| `workflow_manager` | Workflow orchestration (workflow_v2, execution, file_execution, endpoint_v2) |
| `health` | Health check endpoints |
| `plugins` | Plugin system for extensibility |

### URL Routing

- Root URL conf: `backend.base_urls`
- Tenant-scoped: `api/v1/` prefix (configurable via `PATH_PREFIX`)
- API deployments: `deployment/` prefix
- Internal APIs: `internal/` prefix (for worker-to-backend communication)
- Prompt Studio: `prompt-studio/` prefix

### Database

- PostgreSQL 15 with pgvector extension
- Multi-tenancy via `django-tenants` (organization-based)
- Custom DB engine at `backend.custom_db`
- Auth model: `account_v2.User`
- Migrations are per-app in standard Django `migrations/` directories

### Celery Workers

Workers use RabbitMQ as the message broker. Queue architecture:

| Queue | Purpose |
|---|---|
| `celery` | Default tasks |
| `celery_api_deployments` | API deployment processing |
| `celery_periodic_logs` | Periodic log tasks |
| `celery_log_task_queue` | Log processing |
| `file_processing` | File processing pipeline |
| `api_file_processing` | API-triggered file processing |
| `file_processing_callback` | Post-processing callbacks |

Celery Beat handles scheduled tasks via `django_celery_beat.schedulers:DatabaseScheduler`.

### Running Backend Locally

```bash
cd backend
cp sample.env .env  # Configure environment
uv sync --group dev
uv run manage.py migrate
uv run manage.py runserver  # Or use: poe backend
```

Task runner commands (via poethepoet):

```bash
poe backend          # Run with Gunicorn
poe migrate-db       # Run migrations
poe worker           # Default Celery worker
poe beat             # Celery Beat scheduler
poe flower           # Celery monitoring UI
```

## Frontend (React)

### Structure

```
frontend/src/
├── App.jsx           # Root component
├── components/       # Reusable UI components
├── config.js         # Runtime configuration
├── helpers/          # Utility functions
├── hooks/            # Custom React hooks
├── layouts/          # Page layout components
├── pages/            # Route-level page components
├── routes/           # React Router configuration
├── store/            # Zustand state stores
└── setupProxy.js     # Dev proxy configuration
```

### Key Pages

- `ToolIdePage` - Prompt Studio IDE
- `WorkflowsPage` - Workflow management
- `DeploymentsPage` - API deployments
- `ConnectorsPage` - Data connectors
- `SettingsPage` - Platform settings
- `OutputAnalyzerPage` - Extraction output analysis

### State Management

Uses Zustand with individual store files:

- `workflow-store.js` - Workflow state
- `prompt-studio-store.js` - Prompt Studio state
- `session-store.js` - User session
- `custom-tool-store.js` - Custom tools
- Various socket stores for real-time updates via Socket.IO

### Running Frontend Locally

```bash
cd frontend
cp sample.env .env
npm install
npm start           # Development server on port 3000
npm run lint:all    # Run ESLint + Prettier
```

### Linting

- ESLint with `react-app` + Google config + Prettier
- `npm run lint` - Check linting
- `npm run lint:fix` - Auto-fix ESLint issues
- `npm run prettier:fix` - Auto-fix formatting
- `npm run lint:all` - Fix both

## Microservices

All microservices are Flask apps served by Gunicorn in production.

### Platform Service (port 3001)

- Enables tools to interact with the Unstract platform via SDK
- Uses Peewee ORM + PostgreSQL
- Source: `platform-service/src/unstract/platform_service/`

### Prompt Service (port 3003)

- Powers Prompt Studio operations (prompt execution, LLM interactions)
- Uses LlamaIndex for document indexing
- Source: `prompt-service/src/unstract/prompt_service/`

### X2Text Service (port 3004)

- Handles document text extraction
- Supports multiple extractors (LLMWhisperer, Unstructured.io, LlamaIndex Parse)
- Source: `x2text-service/app/`

### Runner (port 5002)

- Manages tool Docker container lifecycle
- Binds Docker socket for container management
- Source: `runner/src/unstract/runner/`

### Workers (Celery, unified architecture)

The `workers/` directory contains a unified Celery worker system with dedicated worker types:

- `api-deployment` - API deployment task processing
- `callback` - Post-processing callbacks
- `file-processing` - Document file processing pipeline
- `general` - General-purpose tasks
- `log-consumer` - Log aggregation and processing
- `notification` - Email/webhook/SMS notifications
- `scheduler` - Scheduled task management

Workers V2 are opt-in via `--workers-v2` Docker Compose profile.

## Core Libraries (`unstract/`)

All packages use `src/unstract/<package_name>/` layout and are installed as editable dependencies.

| Package | PyPI Name | Purpose |
|---|---|---|
| `connectors` | `unstract-connectors` | Data source/destination connector abstractions |
| `core` | `unstract-core` | Shared utilities, base classes, Flask integration |
| `filesystem` | `unstract-filesystem` | Filesystem abstraction layer |
| `flags` | `unstract-flags` | Feature flag client (Flipt integration) |
| `sdk1` | `unstract-sdk1` | SDK for tool development (LLM, embedding, vector DB, file storage) |
| `tool-registry` | `unstract-tool-registry` | Tool discovery and configuration |
| `tool-sandbox` | `unstract-tool-sandbox` | Tool isolation/sandboxing |
| `workflow-execution` | `unstract-workflow-execution` | Workflow execution engine |

## Docker Setup

### Development with Docker

```bash
# Full platform startup
./run-platform.sh

# Or manually:
cd docker
cp sample.env essentials.env
cp sample.compose.override.yaml compose.override.yaml
docker compose up -d
```

### Docker Compose Files

- `docker-compose.yaml` - Main services (backend, frontend, workers, microservices)
- `docker-compose-dev-essentials.yaml` - Infrastructure (PostgreSQL, Redis, MinIO, RabbitMQ, Traefik, Flipt, Qdrant)
- `docker-compose.build.yaml` - Build configurations
- `compose.debug.yaml` - Debug configurations

### Key Infrastructure Services

| Service | Port | Purpose |
|---|---|---|
| PostgreSQL (pgvector) | 5432 | Primary database |
| Redis | 6379 | Cache + session store |
| RabbitMQ | 5672 (AMQP), 15672 (UI) | Message broker for Celery |
| MinIO | 9000 (API), 9001 (Console) | Object storage (S3-compatible) |
| Traefik | 80 (HTTP), 8080 (Dashboard) | Reverse proxy + routing |
| Flipt | 8082 (REST), 9005 (gRPC) | Feature flags |
| Qdrant | 6333 | Vector database |

### Access URLs (Docker)

- Frontend: `http://frontend.unstract.localhost`
- Backend API: `http://frontend.unstract.localhost/api/v1/`
- MinIO Console: `http://minio.unstract.localhost`
- Traefik Dashboard: `http://localhost:8080`
- Flower (Celery Monitor): `http://localhost:5555`
- RabbitMQ Management: `http://localhost:15672`

## Development Workflow

### Package Manager

This project uses **uv** for Python dependency management. Each service and library has its own `pyproject.toml` and `uv.lock`.

```bash
# Install dependencies
uv sync

# Install with dev group
uv sync --group dev

# Add a dependency
uv add <package>

# Run a command
uv run <command>
```

### Pre-commit Hooks

Pre-commit is configured with these hooks (`.pre-commit-config.yaml`):

1. **Standard hooks** - trailing whitespace, end-of-file, YAML/JSON/TOML checks, merge conflicts, private key detection
2. **Ruff** - Python linting and formatting (`ruff --fix` + `ruff-format`)
3. **pycln** - Remove unused imports
4. **pyupgrade** - Upgrade Python syntax to 3.9+
5. **markdownlint** - Markdown linting
6. **gitleaks** - Secret detection
7. **htmlhint** - HTML linting
8. **hadolint** - Dockerfile linting
9. **no-commit-to-branch** - Prevents direct commits to protected branches

Install hooks:

```bash
pre-commit install
```

### Python Linting & Formatting

Configured in root `pyproject.toml`:

- **Ruff** (linter + formatter): line length 90, Python 3.12 target
  - Rules: E, F, I (isort), B (bugbear), W, C90 (complexity), N (naming), D (docstrings), UP (pyupgrade), ANN (annotations), TCH (type-checking), PYI
  - Docstring convention: Google style
  - Quote style: double quotes
  - Indent style: spaces
- **pycln**: Remove unused imports
- **mypy**: Strict mode, Python 3.12

```bash
# Run ruff linting
ruff check .

# Run ruff formatting
ruff format .

# Run mypy
mypy .
```

### Testing

Tests use pytest. Configuration in root `pyproject.toml`:

```bash
# Run backend tests
cd backend
uv run pytest

# Run runner tests
tox -e runner

# Run SDK tests
tox -e sdk1

# Run with markers
pytest -m "not slow"
pytest -m "not integration"
```

Test markers: `slow`, `integration`, `unit`

Django test settings: `backend.settings.test_cases` (via `DJANGO_SETTINGS_MODULE` in pytest config)

### Database Migrations

```bash
cd backend
uv run manage.py makemigrations <app_name>
uv run manage.py migrate

# Check for missing migrations (CI hook)
uv run manage.py makemigrations --check
```

## Key Conventions

### Python Code Style

- Line length: 90 characters
- Import sorting: isort (via ruff)
- Docstrings: Google convention
- Type hints: Encouraged but many ignores configured (see ruff ignore list)
- String quotes: Double quotes
- No direct commits to `main` branch

### Django Patterns

- Apps use `_v2` suffix (legacy `v1` apps exist but are being phased out)
- ViewSets with DRF serializers for API endpoints
- Custom middleware for organization/tenant context (`middleware/organization_middleware.py`)
- Internal API authentication (`middleware/internal_api_auth.py`)
- Plugin architecture in `backend/plugins/` for extensibility

### Frontend Patterns

- Functional components with hooks
- Zustand for state management (not Redux)
- Ant Design component library
- Socket.IO for real-time log streaming
- Pages correspond to major features (Workflows, Deployments, Prompt Studio, etc.)

### Environment Configuration

Each service uses `.env` files (copy from `sample.env`):

- `backend/.env` - Backend + worker configuration
- `platform-service/.env` - Platform service
- `prompt-service/.env` - Prompt service
- `runner/.env` - Runner service
- `workers/.env` - Unified workers
- `x2text-service/.env` - X2Text service
- `docker/essentials.env` - Infrastructure services (DB, Redis, RabbitMQ)
- `frontend/.env` - Frontend build-time config

**Critical**: The `ENCRYPTION_KEY` in `backend/.env` and `platform-service/.env` encrypts adapter credentials. Loss or change makes all existing adapters inaccessible.

### Inter-service Communication

- Backend communicates with microservices via HTTP (platform-service:3001, prompt-service:3003, x2text-service:3004, runner:5002)
- Workers communicate with backend via internal API (`/internal/` endpoints) authenticated by `INTERNAL_SERVICE_API_KEY`
- Celery tasks dispatched via RabbitMQ
- Real-time updates via Socket.IO (frontend <-> backend)
- Runner manages tool containers via Docker socket

### Multitenancy

The platform uses organization-based multitenancy:

- `django-tenants` for tenant isolation
- Organization middleware sets tenant context per request
- Public endpoints use a separate URL namespace
- Each organization has isolated data within the shared database schema

## CI/CD Notes

- Pre-commit CI runs on all PRs
- SonarCloud for code quality analysis
- Migration checks: `uv run manage.py makemigrations --check` (hook-check-django-migrations dependency group)
- tox environments: `py312` (default), `runner`, `sdk1`
