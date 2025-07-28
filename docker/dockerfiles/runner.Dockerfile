# Use a specific version of Python slim image
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Runner Service Container" \
    version="${VERSION}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=runner \
    BUILD_PACKAGES_PATH=unstract \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_runner

# Install system dependencies
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       docker \
       git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create working directory
WORKDIR ${APP_HOME}

# -----------------------------------------------
# EXTERNAL DEPENDENCIES STAGE - This layer gets cached if external dependencies don't change
# -----------------------------------------------
FROM base AS ext-dependencies

# Copy dependency-related files
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY ${BUILD_PACKAGES_PATH}/flags /unstract/flags

# Install external dependencies from pyproject.toml
RUN uv sync --group deploy --locked --no-install-project --no-dev

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Set shell options for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Copy application code (this layer changes most frequently)
COPY ${BUILD_CONTEXT_PATH} ./

# Install the application
RUN uv sync --group deploy --no-dev --locked

# Install cloud requirements if they exist and setup OTEL
RUN if [ -f cloud_requirements.txt ]; then \
        uv pip install -r cloud_requirements.txt; \
    else \
        echo "cloud_requirements.txt does not exist"; \
    fi && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -

EXPOSE 5002

CMD [ "./entrypoint.sh" ]
