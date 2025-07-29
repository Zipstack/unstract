# Development File Processing Worker Dockerfile
# Optimized for fast development builds with volume mounts
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="File Processing Worker Container (Development)" \
    version="${VERSION}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    WORKER_TYPE=file_processing \
    APP_HOME=/app

# Install system dependencies
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       curl \
       gcc \
       libmagic-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create working directory
WORKDIR ${APP_HOME}

# -----------------------------------------------
# DEPENDENCIES STAGE - Cache heavy dependencies
# -----------------------------------------------
FROM base AS dependencies

# Copy only dependency files for caching
COPY workers/file_processing/pyproject.toml /app/workers/file_processing/
COPY workers/file_processing/uv.lock /app/workers/file_processing/
COPY workers/pyproject.toml /app/workers/
COPY workers/shared/pyproject.toml /app/workers/shared/

# Copy unstract package files (minimal for dependency resolution)
COPY unstract/connectors/pyproject.toml /app/unstract/connectors/
COPY unstract/core/pyproject.toml /app/unstract/core/
COPY unstract/filesystem/pyproject.toml /app/unstract/filesystem/
COPY unstract/flags/pyproject.toml /app/unstract/flags/
COPY unstract/tool-registry/pyproject.toml /app/unstract/tool-registry/
COPY unstract/tool-sandbox/pyproject.toml /app/unstract/tool-sandbox/
COPY unstract/workflow-execution/pyproject.toml /app/unstract/workflow-execution/

# Create minimal package structure for editable installs
RUN mkdir -p /app/unstract/connectors/src/unstract \
    && mkdir -p /app/unstract/core/src/unstract \
    && mkdir -p /app/unstract/filesystem/src/unstract \
    && mkdir -p /app/unstract/flags/src/unstract \
    && mkdir -p /app/unstract/tool-registry/src/unstract \
    && mkdir -p /app/unstract/tool-sandbox/src/unstract \
    && mkdir -p /app/unstract/workflow-execution/src/unstract \
    && mkdir -p /app/workers/shared

# Create minimal __init__.py files for packages
RUN touch /app/unstract/connectors/src/unstract/__init__.py \
    && touch /app/unstract/core/src/unstract/__init__.py \
    && touch /app/unstract/filesystem/src/unstract/__init__.py \
    && touch /app/unstract/flags/src/unstract/__init__.py \
    && touch /app/unstract/tool-registry/src/unstract/__init__.py \
    && touch /app/unstract/tool-sandbox/src/unstract/__init__.py \
    && touch /app/unstract/workflow-execution/src/unstract/__init__.py \
    && touch /app/workers/shared/__init__.py

# Set working directory and install dependencies
WORKDIR /app/workers/file_processing
RUN uv sync --locked --no-install-project --no-dev

# -----------------------------------------------
# DEVELOPMENT STAGE - Volume mounts for live reload
# -----------------------------------------------
FROM dependencies AS development

# Create non-root user for security
RUN groupadd -r celery && useradd -r -g celery celery
RUN chown -R celery:celery /app
USER celery

# Expose health check port
EXPOSE ${HEALTH_PORT:-8082}

# In development, source code will be mounted as volumes
# This allows for live code reloading without rebuilds
CMD ["/app/workers/file_processing/.venv/bin/python", "-m", "worker"]
