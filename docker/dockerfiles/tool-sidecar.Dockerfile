# Use Python 3.9 alpine for minimal size
FROM python:3.9-slim
LABEL maintainer="Zipstack Inc."

ENV \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOG_PATH=/shared/logs/logs.txt \
    LOG_LEVEL=INFO \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=tool-sidecar \
    BUILD_PACKAGES_PATH=unstract \
    PDM_VERSION=2.16.1 \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_tool_sidecar \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get --no-install-recommends install -y docker \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
    \
    && pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}

WORKDIR /app

# Create venv and install gunicorn and other deps in it
RUN pdm venv create -w virtualenv --with-pip && \
    . .venv/bin/activate

# Copy local dependency packages first
COPY ${BUILD_PACKAGES_PATH}/core /unstract/core

# Copy application files
COPY ${BUILD_CONTEXT_PATH} /app/

# Ensure correct package structure
RUN touch /app/src/unstract/__init__.py && \
    cd /unstract/core && pip install --no-cache-dir -e . && cd /app && \
    pip install --no-cache-dir -e . && \
    . .venv/bin/activate && \
    pdm sync --prod --no-editable --with deploy && \
    opentelemetry-bootstrap -a install

COPY ${BUILD_CONTEXT_PATH}/entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

CMD ["./entrypoint.sh"]
