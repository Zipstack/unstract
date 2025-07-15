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

1. Make changes to your code in your local editor
1. Changes are automatically synced to the container and services restart as needed
1. For debugging:
   - Configure IDE to connect to the appropriate debugpy port
   Here's an example `launch.json` (for VSCode) to attach to a the `backend` container on port 5678.
   It assumes that a workspace involving unstract and unstract-sdk is setup.
   For more information on this refer [VSCode docs](https://code.visualstudio.com/docs/devcontainers/attach-container#_attach-to-a-docker-container).

   ```json
    {
      "name": "Docker: Backend Remote Debug",
      "type": "debugpy",
      "request": "attach",
      "connect": {
        "host": "localhost",
        "port": 5678
      },
      "pathMappings": [
        {
          "localRoot": "${workspaceFolder:unstract}/backend",
          "remoteRoot": "/app"
        },
        {
          "localRoot": "${workspaceFolder:unstract}/unstract",
          "remoteRoot": "/unstract"
        },
        // Uncomment below to use and debug local version of unstract-sdk
        // {
        // 	"localRoot": "${workspaceFolder:unstract-sdk}/src/unstract/sdk",
        // 	"remoteRoot": "/unstract-sdk/src/unstract/sdk"
        // },
      ],
      "justMyCode": false,
      "django": true,
      "presentation": {
        "group": "docker-debug"
      }
    }
   ```

   - Set breakpoints in your code
   - Trigger the code path and the debugger will pause at your breakpoints

1. View logs in real-time:

   ```bash
   docker compose logs -f [service_name]
   ```

This workflow eliminates the need to rebuild containers or manually restart services during development, significantly improving productivity.

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
