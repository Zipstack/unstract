# Use a specific version of Python slim image
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Prompt Service Container" \
    version="${VERSION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
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
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       build-essential \
       libmagic-dev \
       pkg-config \
       git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
    && adduser -u 5678 --disabled-password --gecos "" ${APP_USER} \
    && mkdir -p ${APP_HOME} \
    && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create working directory
WORKDIR ${APP_HOME}

# -----------------------------------------------
# EXTERNAL DEPENDENCIES STAGE - This layer gets cached if external dependencies don't change
# -----------------------------------------------
FROM base AS ext-dependencies

# Copy dependency-related files
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ${BUILD_CONTEXT_PATH}/README.md ./

# Copy local package dependencies
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/sdk1 /unstract/sdk1
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=${APP_USER}:${APP_USER} ${BUILD_PACKAGES_PATH}/flags /unstract/flags

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

# Install just the application in editable mode
RUN uv sync --group deploy --locked

# Install plugins after copying source code
RUN for dir in "${TARGET_PLUGINS_PATH}"/*/; do \
    dirpath=${dir%*/}; \
    dirname=${dirpath##*/}; \
    if [ "${dirname}" != "*" ]; then \
    echo "Installing plugin: ${dirname}..." && \
    uv pip install "${TARGET_PLUGINS_PATH}/${dirname}"; \
    fi; \
    done && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement -

# Create required directories
RUN mkdir -p prompt-studio-data

EXPOSE 3003

CMD ["./entrypoint.sh"]
