# Docker Build

```bash
# Build all services
VERSION=llama_test docker compose -f docker-compose.build.yaml build

# Build a specific service alone
VERSION=dev docker compose -f docker-compose.build.yaml build frontend
```

# Docker Run

**NOTE**: First copy `sample.*.env` files to `*.env` and update as required.

```bash
# Up all services
VERSION=llama_test docker compose -f docker-compose.yaml up -d

# Up a specific service alone
VERSION=dev docker compose -f docker-compose.yaml up -d frontend
```

Now access frontend at http://frontend.unstract.localhost

# Docker Build and Run Optional Services

Some services are kept optional and will not be built or started by default. Run them as follows.

```bash
# Build optional services also
VERSION=dev docker compose -f docker-compose.build.yaml --profile optional build
# Up optional services also
VERSION=dev docker compose -f docker-compose.yaml --profile optional up -d
```

# `src` Folder Layout and `gunicorn`

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
