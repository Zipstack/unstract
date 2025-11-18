# Single-stage build with cache mounts for optimal performance
FROM python:3.12-slim-trixie

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Platform Service Container" \
    version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=platform-service \
    BUILD_PACKAGES_PATH=unstract \
    APP_USER=unstract \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_platform

# Create working directory
WORKDIR ${APP_HOME}

# Set shell options for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Install system dependencies and create user in one layer with cache mounts
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get --no-install-recommends install -y \
        build-essential \
        libmagic-dev \
        git && \
    adduser -u 5678 --disabled-password --gecos "" ${APP_USER} && \
    mkdir -p ${APP_HOME} && \
    chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Copy dependency-related files
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/sdk1 /unstract/sdk1
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/flags /unstract/flags

# Switch to non-root user for dependency installation
USER ${APP_USER}

# Install external dependencies from pyproject.toml with cache mount
# This layer is cached when dependencies don't change
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    UV_LINK_MODE=copy uv sync --group deploy --locked --no-install-project --no-dev

# Copy application code (this layer changes most frequently)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Install the application in non-editable mode to avoid permission issues with cache mount
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    UV_LINK_MODE=copy uv sync --group deploy --locked && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -

EXPOSE 3001

ENTRYPOINT [ "./entrypoint.sh" ]
