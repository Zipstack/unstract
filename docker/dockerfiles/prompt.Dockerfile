# Use a specific version of Python slim image
FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc." \
    description="Prompt Service Container" \
    version="1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
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

# Install system dependencies, create user, and setup directories in one layer
RUN apt-get update && \
    apt-get --no-install-recommends install -y \
    build-essential \
    libmagic-dev \
    pkg-config \
    git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* && \
    adduser -u 5678 --disabled-password --gecos "" ${APP_USER} && \
    mkdir -p ${APP_HOME} && \
    chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR ${APP_HOME}

# Copy dependency files first for better caching
COPY --chown=${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ./

# Copy required packages
COPY --chown=${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=${APP_USER} ${BUILD_PACKAGES_PATH}/flags /unstract/flags

# Copy application code
COPY --chown=${APP_USER} ${BUILD_CONTEXT_PATH} /app/

# Switch to non-root user
USER ${APP_USER}

# Install dependencies in a single layer
RUN uv sync --frozen && \
    uv sync && \
    . .venv/bin/activate && \
    for dir in "${TARGET_PLUGINS_PATH}"/*/; do \
    dirpath=${dir%*/}; \
    if [ "${dirpath##*/}" != "*" ]; then \
    cd "$dirpath" && \
    echo "Installing plugin: ${dirpath##*/}..." && \
    uv sync && \
    cd -; \
    fi; \
    done && \
    uv sync --group deploy && \
    uv run opentelemetry-bootstrap -a install && \
    mkdir -p prompt-studio-data

EXPOSE 3003

# Default command
CMD ["./entrypoint.sh"]
