# Use Python 3.12.9-slim for minimal size
FROM python:3.12-slim-trixie

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

# Install system dependencies with cache mounts
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get --no-install-recommends install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    build-essential \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get --no-install-recommends install -y docker-ce-cli \
    && adduser --uid 5678 --disabled-password --gecos "" ${APP_USER} \
    && mkdir -p ${APP_HOME} \
    && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR ${APP_HOME}

# Copy dependency-related files
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core

# Switch to non-root user
USER ${APP_USER}

# Install external dependencies from pyproject.toml with cache mount
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    uv sync --group deploy --locked --no-install-project --no-dev --link-mode=copy

# Copy application code (this layer changes most frequently)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Install the application with cache mount
RUN --mount=type=cache,target=/home/unstract/.cache/uv,uid=5678,gid=5678 \
    uv sync --group deploy --locked --link-mode=copy && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement - && \
    chmod +x ./entrypoint.sh

CMD ["./entrypoint.sh"]
