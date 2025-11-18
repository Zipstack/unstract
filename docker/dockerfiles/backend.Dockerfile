# Single-stage build with cache mounts for optimal performance
FROM python:3.12-slim-trixie

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Backend Service Container" \
    version="${VERSION}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=backend \
    BUILD_PACKAGES_PATH=unstract \
    DJANGO_SETTINGS_MODULE="backend.settings.dev" \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_backend

# Create working directory
WORKDIR ${APP_HOME}

# Set shell options for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Install system dependencies with cache mounts
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get --no-install-recommends install -y \
        build-essential \
        freetds-dev \
        git \
        libkrb5-dev \
        libmagic-dev \
        libssl-dev \
        pkg-config

# Copy dependency-related files
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY ${BUILD_PACKAGES_PATH}/ /unstract/

# Install external dependencies from pyproject.toml with cache mount
# This layer is cached when dependencies don't change
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv sync --group deploy --locked --no-install-project --no-dev

# Copy application code (this layer changes most frequently)
COPY ${BUILD_CONTEXT_PATH}/ ./

# Install the application with cache mount
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv sync --group deploy --locked && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement - && \
    chmod +x ./entrypoint.sh

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
