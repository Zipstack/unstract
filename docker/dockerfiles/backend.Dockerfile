FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc."

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=backend \
    BUILD_PACKAGES_PATH=unstract \
    DJANGO_SETTINGS_MODULE="backend.settings.dev" \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_backend

# Install system dependencies
RUN apt-get update && \
    apt-get --no-install-recommends install -y \
    build-essential \
    freetds-dev \
    git \
    libkrb5-dev \
    libmagic-dev \
    libssl-dev \
    pkg-config && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR /app

# Copy only what's needed for dependency installation first
COPY pyproject.toml uv.lock /app/

# Copy source code and dependencies
COPY ${BUILD_CONTEXT_PATH}/ /app/
COPY ${BUILD_PACKAGES_PATH}/ /unstract/

# Install dependencies in one layer
RUN uv sync --frozen && \
    uv sync --group deploy && \
    .venv/bin/python3 -m ensurepip --upgrade && \
    uv run opentelemetry-bootstrap -a install

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]

#  Patched code
WORKDIR /app

RUN set -e; \
    uv add -r requirements.txt

ENV DJANGO_SETTINGS_MODULE=backend.settings.cloud
WORKDIR /app

