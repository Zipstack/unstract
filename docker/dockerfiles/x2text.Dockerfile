# Use a specific version of Python slim image
FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc." \
    description="X2Text Service Container" \
    version="1.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUILD_CONTEXT_PATH=x2text-service \
    APP_USER=unstract \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_x2text

# Install system dependencies and create user in a single layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --uid 5678 --disabled-password --gecos "" ${APP_USER} \
    && mkdir -p ${APP_HOME} \
    && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR ${APP_HOME}

# Copy only requirements files first to leverage Docker cache
COPY --chmod=755 ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ./

# Switch to non-root user
USER ${APP_USER}

# Install dependencies
RUN uv sync --frozen \
    && uv sync --group deploy \
    && uv run opentelemetry-bootstrap -a install

# Copy application code
COPY --chmod=755 --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} .

EXPOSE 3004

# During debugging, this entry point will be overridden.
# For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3004", "--timeout", "300", "run:app"]
