# Use Python 3.12.9-slim for minimal size
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Tool Sidecar Container" \
    version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_PATH=/shared/logs/logs.txt \
    LOG_LEVEL=INFO \
    BUILD_PACKAGES_PATH=unstract \
    BUILD_CONTEXT_PATH=tool-sidecar \
    APP_USER=unstract \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_tool_sidecar \
    PATH="/app/.venv/bin:$PATH"

# Install system dependencies in a single layer
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       docker \
       build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
    && adduser --uid 5678 --disabled-password --gecos "" ${APP_USER} \
    && mkdir -p ${APP_HOME} \
    && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR ${APP_HOME}

# -----------------------------------------------
# EXTERNAL DEPENDENCIES STAGE
# -----------------------------------------------
FROM base AS ext-dependencies

# Copy dependency-related files
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core

# Switch to non-root user
USER ${APP_USER}

# Install external dependencies from pyproject.toml
RUN uv sync --group deploy --locked --no-install-project --no-dev && \
    .venv/bin/python3 -m ensurepip --upgrade && \
    uv run opentelemetry-bootstrap -a install

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Copy application code (this layer changes most frequently)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Switch to non-root user
USER ${APP_USER}

# Install just the application
RUN uv sync --group deploy --locked && \
    chmod +x ./entrypoint.sh

# # Make entrypoint executable
# RUN chmod +x ./entrypoint.sh

CMD ["./entrypoint.sh"]
