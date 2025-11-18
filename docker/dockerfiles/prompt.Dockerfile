# Use a specific version of Python slim image
FROM python:3.12-slim-trixie

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Prompt Service Container" \
    version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=prompt-service \
    BUILD_PACKAGES_PATH=unstract \
    TARGET_PLUGINS_PATH=src/unstract/prompt_service/plugins \
    APP_USER=unstract \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_prompt

# Install system dependencies, create user, and setup directories with cache mounts
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get --no-install-recommends install -y \
    build-essential \
    libmagic-dev \
    pkg-config \
    git \
    && adduser -u 5678 --disabled-password --gecos "" ${APP_USER} \
    && mkdir -p ${APP_HOME} \
    && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create working directory
WORKDIR ${APP_HOME}

# Set shell options for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Copy dependency-related files
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/sdk1 /unstract/sdk1
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/flags /unstract/flags

# Switch to non-root user
USER ${APP_USER}

# Install external dependencies from pyproject.toml with cache mount
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    uv sync --group deploy --locked --no-install-project --no-dev --link-mode=copy

# Copy application code (this layer changes most frequently)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Install the application in editable mode with cache mount
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    uv sync --group deploy --locked --link-mode=copy

# Install plugins after copying source code with cache mount
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    for dir in "${TARGET_PLUGINS_PATH}"/*/; do \
    dirpath=${dir%*/}; \
    dirname=${dirpath##*/}; \
    if [ "${dirname}" != "*" ]; then \
    echo "Installing plugin: ${dirname}..." && \
    uv pip install "${TARGET_PLUGINS_PATH}/${dirname}"; \
    fi; \
    done && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -

# Create required directories
RUN mkdir -p prompt-studio-data

EXPOSE 3003

CMD ["./entrypoint.sh"]
