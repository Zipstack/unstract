# Use a specific version of Python slim image
FROM python:3.12-slim-trixie  AS base

LABEL maintainer="Zipstack Inc." \
    description="X2Text Service Container"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BUILD_CONTEXT_PATH=x2text-service \
    BUILD_PACKAGES_PATH=unstract \
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

# Copy local package dependencies (unstract-core provides the SSRF guard)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core

# Switch to non-root user
USER ${APP_USER}

# Install external dependencies from pyproject.toml
RUN uv sync --group deploy --locked --no-install-project --no-dev

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Set shell options for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Copy application code (this layer changes most frequently)
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH} ./

# Switch to non-root user
USER ${APP_USER}

# Install just the application
RUN uv sync --group deploy --locked && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -

EXPOSE 3004

ARG VERSION=dev
ENV UNSTRACT_APPS_VERSION=${VERSION}

# During debugging, this entry point will be overridden.
# This CMD runs gunicorn's default sync worker, which the arbiter kills once it
# has been busy in one request for longer than --timeout. 930s keeps that above
# the Unstructured read timeout (UNSTRUCTURED_REQUEST_TIMEOUT, 900s default), so
# a call that spends its time in processing ends in a 504 rather than a killed
# worker; the 30s of headroom also has to cover the connect and the upload.
# (The Helm chart runs its own entrypoint with gthread workers, which keep
# heartbeating during a request, so --timeout does not end long calls there.)
# One sync worker means a long call holds it; GUNICORN_CMD_ARGS="--workers 4"
# adds workers, but cannot override --timeout, which is set here on the CLI.
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3004", "--timeout", "930", "run:app"]
