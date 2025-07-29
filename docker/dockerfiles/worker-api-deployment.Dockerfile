# API Deployment Worker Dockerfile
# Use a specific version of Python slim image
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="API Deployment Worker Container" \
    version="${VERSION}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    WORKER_TYPE=api_deployment \
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
# EXTERNAL DEPENDENCIES STAGE - This layer gets cached if external dependencies don't change
# -----------------------------------------------
FROM base AS ext-dependencies

# Copy entire workers directory structure
COPY workers /app/workers

# Copy unstract packages
COPY unstract /app/unstract

# Set working directory to the specific worker
WORKDIR /app/workers/api-deployment

# Install external dependencies from pyproject.toml
RUN uv sync --locked --no-install-project --no-dev

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Ensure we're in the correct directory
WORKDIR /app/workers/api-deployment

# Create non-root user for security
RUN groupadd -r celery && useradd -r -g celery celery
RUN chown -R celery:celery /app
USER celery

# Health check endpoint available at runtime (no Docker HEALTHCHECK)
# Expose health check port
EXPOSE ${HEALTH_PORT:-8080}

# Default command - can be overridden
CMD ["/app/workers/api-deployment/.venv/bin/python", "-m", "worker"]
