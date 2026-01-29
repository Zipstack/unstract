# Docker Commands

## Docker Build

```bash
# Build all services
VERSION=dev docker compose -f docker-compose.build.yaml build

# Build a specific service alone
VERSION=dev docker compose -f docker-compose.build.yaml build frontend

# Build optional services also
VERSION=dev docker compose -f docker-compose.build.yaml --profile optional build
```

## Docker Run

**NOTE**: First copy `sample.*.env` files to `*.env` and update as required.

```bash
# Up all services
VERSION=dev docker compose -f docker-compose.yaml up -d

# Up a specific service alone
VERSION=dev docker compose -f docker-compose.yaml up -d frontend

# Up optional services also
VERSION=dev docker compose -f docker-compose.yaml --profile optional up -d
```

Now access frontend at http://frontend.unstract.localhost

## V2 Workers (Optional)

V2 workers use a unified container architecture and are **disabled by default**.

```bash
# Default: Run with legacy workers only
VERSION=dev docker compose -f docker-compose.yaml up -d

# Enable V2 workers (unified container)
VERSION=dev docker compose -f docker-compose.yaml --profile workers-v2 up -d

# Or use the platform script
./run-platform.sh --workers-v2
```

V2 workers available: `api-deployment`, `callback`, `file-processing`, `general`, `notification`, `log-consumer`, `scheduler`

## Overriding a service's config

By making use of the [merge compose files](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) feature its possible to override some configuration that's used by the services.

Copy and rename the `sample.compose.override.yaml` to `compose.override.yaml` and update it as necessary.

```bash
cp sample.compose.override.yaml compose.override.yaml

# Configuration in docker-compose.yaml gets overridden
VERSION=dev docker compose -f docker-compose.yaml -f compose.override.yaml up -d
```

This can be useful during development to:

- Not run some memory intensive services
- Use commands with different arguments to save resources
- Mount additional volumes or define additional env to configure behaviour

## Development with Docker Compose Watch

[Docker Compose Watch](https://docs.docker.com/compose/how-tos/file-watch/) (available in Docker Compose v2.22.0+) enables a streamlined development workflow by automatically syncing code changes to containers and restarting services as needed.

### Setting Up Watch Mode

1. Ensure you're using Docker Compose v2.22.0 or higher

   ```bash
   docker compose version
   ```

2. Create your `compose.override.yaml` with watch configurations

   ```bash
   cp sample.compose.override.yaml compose.override.yaml
   ```

3. Start services with watch mode enabled

   ```bash
   VERSION=dev docker compose -f docker-compose.yaml -f compose.override.yaml watch
   ```

> **NOTE**: Make sure to specify the build definitions also in your `compose.override.yaml` file or specify [docker-compose.build.yaml](/docker/docker-compose.build.yaml) while running the above command.

### Example Workflow

1. Start services with watch mode:

   ```bash
   VERSION=dev docker compose -f docker-compose.yaml -f compose.override.yaml watch
   ```

2. Make changes to your code - they're automatically synced and services restart as needed

3. View logs: `docker compose logs -f [service_name]`

## Debugging Containers

Enable debugpy by adding `compose.debug.yaml`:

```bash
VERSION=dev docker compose -f docker-compose.yaml -f compose.override.yaml -f compose.debug.yaml watch
```

Debug ports per service:

| Service | Port |
|---------|------|
| backend | 5678 |
| runner | 5679 |
| platform-service | 5680 |
| prompt-service | 5681 |
| **V2 Workers** | |
| worker-file-processing-v2 | 5682 |
| worker-callback-v2 | 5683 |
| worker-api-deployment-v2 | 5684 |
| worker-general-v2 | 5685 |
| worker-notification-v2 | 5686 |
| worker-log-consumer-v2 | 5687 |
| worker-scheduler-v2 | 5688 |

### VSCode Configuration

Example `launch.json` to attach to the `backend` container:

```json
{
  "name": "Docker: Backend Remote Debug",
  "type": "debugpy",
  "request": "attach",
  "connect": { "host": "localhost", "port": 5678 },
  "pathMappings": [
    { "localRoot": "${workspaceFolder:unstract}/backend", "remoteRoot": "/app" },
    { "localRoot": "${workspaceFolder:unstract}/unstract", "remoteRoot": "/unstract" }
  ],
  "justMyCode": false,
  "django": true
}
```

See [VSCode docs](https://code.visualstudio.com/docs/devcontainers/attach-container#_attach-to-a-docker-container) for more details.

## `src` Folder Layout and `gunicorn`

For the following project structure:

```bash
scheduler
  |- src
  |   |- unstract
  |       |- scheduler
  |           |- main.py
  |- uv.lock
  |- pyproject.toml
```

This will install the project to:

```bash
.venv/lib/python3.12/site-packages/unstract/scheduler/main.py
```

This will allow `gunicorn` to refer the package directly as:

```bash
$ gunicorn "-c" "python:unstract.scheduler.config.gunicorn" "unstract.scheduler.main:app"
```
