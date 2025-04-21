# Use a specific version of Python slim image
FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc." \
    description="Platform Service Container" \
    version="1.0"

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
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

# Install system dependencies and create user in one layer
RUN apt-get update && \
    apt-get --no-install-recommends install -y build-essential libmagic-dev git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* && \
    adduser -u 5678 --disabled-password --gecos "" ${APP_USER} && \
    mkdir -p ${APP_HOME} && \
    chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR ${APP_HOME}

# Copy dependency files first to leverage Docker cache
COPY --chown=${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ./

# Read and execute access to non-root user to avoid security hotspot
# Write access to specific sub-directory need to be explicitly provided if required
COPY --chown=${APP_USER} ${BUILD_CONTEXT_PATH} /app/
# Copy local dependency packages
COPY --chown=${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=${APP_USER} ${BUILD_PACKAGES_PATH}/flags /unstract/flags

# Copy application files
COPY --chown=${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Switch to non-root user
USER ${APP_USER}

# Create virtual environment and install dependencies in one layer
RUN uv sync --frozen \
    && uv sync --group deploy \
    && .venv/bin/python3 -m ensurepip --upgrade \
    && uv run opentelemetry-bootstrap -a install

EXPOSE 3001

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3001", "--timeout", "300", "unstract.platform_service.run:app"]
