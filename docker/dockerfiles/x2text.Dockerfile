# Use a specific version of Python slim image
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="X2Text Service Container" \
    version="${VERSION}"

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
    && apt-get install -y --no-install-recommends \
       build-essential \
       libmagic-dev \
       pkg-config \
       git \
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
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Install external dependencies from pyproject.toml
RUN uv sync --group deploy --locked --no-install-project --no-dev && \
    uv run opentelemetry-bootstrap -a install

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Copy application code (this layer changes most frequently)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Install just the application
RUN uv sync --group deploy --locked

# Switch to non-root user
USER ${APP_USER}

EXPOSE 3004

# During debugging, this entry point will be overridden.
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3004", "--timeout", "300", "run:app"]
