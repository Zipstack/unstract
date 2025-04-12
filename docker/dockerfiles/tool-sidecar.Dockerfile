# Use Python 3.12.9-slim for minimal size
FROM python:3.12.9-slim
LABEL maintainer="Zipstack Inc."

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_PATH=/shared/logs/logs.txt \
    LOG_LEVEL=INFO \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=tool-sidecar \
    BUILD_PACKAGES_PATH=unstract \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_tool_sidecar \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get --no-install-recommends install -y docker \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR /app

# Copy local dependency packages first
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml .
COPY ${BUILD_CONTEXT_PATH}/uv.lock .

# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/core /unstract/core

# Copy application files
COPY ${BUILD_CONTEXT_PATH} /app/

# Install dependencies in a single layer
RUN uv sync --frozen \
    && uv sync --group deploy \
    && .venv/bin/python3 -m ensurepip --upgrade \
    && uv run opentelemetry-bootstrap -a install

COPY ${BUILD_CONTEXT_PATH}/entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

CMD ["./entrypoint.sh"]
