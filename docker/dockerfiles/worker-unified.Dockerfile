# Unified Worker Dockerfile - Optimized for fast builds
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Unified Worker Container for All Worker Types" \
    version="${VERSION}"

# Set environment variables (CRITICAL: PYTHONPATH makes paths work!)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/unstract \
    BUILD_CONTEXT_PATH=workers \
    BUILD_PACKAGES_PATH=unstract \
    APP_HOME=/app \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_workers

# Install system dependencies (minimal for workers)
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       build-essential \
       curl \
       gcc \
       libmagic-dev \
       libssl-dev \
       pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create non-root user early to avoid ownership issues
RUN groupadd -r worker && useradd -r -g worker worker && \
    mkdir -p /home/worker && chown -R worker:worker /home/worker

# Create working directory
WORKDIR ${APP_HOME}

# -----------------------------------------------
# EXTERNAL DEPENDENCIES STAGE - This layer gets cached
# -----------------------------------------------
FROM base AS ext-dependencies

# Copy dependency files (including README.md like backend)
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ./
# Create empty README.md if it doesn't exist in the copy
RUN touch README.md

# Copy local package dependencies to /unstract directory
# This provides the unstract packages for imports
COPY ${BUILD_PACKAGES_PATH}/ /unstract/

# Install external dependencies with --locked for FAST builds
# No symlinks needed - PYTHONPATH handles the paths
RUN uv sync --group deploy --locked --no-install-project --no-dev

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Copy application code (this layer changes most frequently)
COPY ${BUILD_CONTEXT_PATH}/ ./

# Set shell with pipefail for proper error handling in pipes
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install project and OpenTelemetry instrumentation (as root to avoid permission issues)
# No symlinks needed - PYTHONPATH handles the paths correctly
RUN uv sync --group deploy --locked && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement - && \
    { chmod +x ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true; } && \
    touch requirements.txt && \
    { chown -R worker:worker ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true; }

# Pre-download tiktoken encodings to avoid runtime network calls
RUN uv run python -c "import tiktoken; tiktoken.encoding_for_model('gpt-3.5-turbo'); tiktoken.encoding_for_model('gpt-4')"

# Switch to worker user
USER worker


# Default command - runs the Docker-optimized worker script
ENTRYPOINT ["/app/run-worker-docker.sh"]
CMD ["general"]
