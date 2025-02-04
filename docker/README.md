# Docker Commands

## Docker Build

```bash
# Build all services
VERSION=dev docker compose -f docker-compose.build.yaml build

# Build a specific service alone
VERSION=dev docker compose -f docker-compose.build.yaml build frontend
```

## Docker Run

**NOTE**: First copy `sample.*.env` files to `*.env` and update as required.

```bash
# Up all services
VERSION=dev docker compose -f docker-compose.yaml up -d

# Up a specific service alone
VERSION=dev docker compose -f docker-compose.yaml up -d frontend
```

Now access frontend at http://frontend.unstract.localhost

## Docker Build and Run Optional Services

Some services are kept optional and will not be built or started by default. Run them as follows.

```bash
# Build optional services also
VERSION=dev docker compose -f docker-compose.build.yaml --profile optional build
# Up optional services also
VERSION=dev docker compose -f docker-compose.yaml --profile optional up -d
```

## Overriding a service's config

By making use of the [merge compose files](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/) feature its
possible to override some configuration that's used by the services.

Copy and rename the `sample.compose.override.yaml` to `compose.override.yaml` and update it as necessary.

```bash
cp sample.compose.override.yaml compose.override.yaml

# Configuration in docker-compose.yaml gets overridden
VERSION=dev docker compose -f docker-compose.yaml -f compose.override.yaml up -d
```

This can be useful during development to

- not run some memory intensive services
- use commands with different arguments to save resources
- mount additional volumes or define additional env to configure behaviour

## `src` Folder Layout and `gunicorn`

For the following project structure:

```bash
scheduler
  |- src
  |   |- unstract
  |       |- scheduler
  |           |- main.py
  |- pdm.lock
  |- pyproject.toml
```

Add the following in `pyproject.toml` to detect package in `src`:

```pyproject.toml
[tool.pdm.build]
includes = ["src"]
package-dir = "src"
```

This will install the project to:

```bash
.venv/lib/python3.12/site-packages/unstract/scheduler/main.py
```

This will allow `gunicorn` to refer the package directly as:

```bash
$ gunicorn "-c" "python:unstract.scheduler.config.gunicorn" "unstract.scheduler.main:app"
```
