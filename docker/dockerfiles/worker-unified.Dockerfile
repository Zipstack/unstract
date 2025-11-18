# Single-stage Unified Worker - Optimized for fast builds with cache mounts
FROM python:3.12.9-slim

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

# Create working directory
WORKDIR ${APP_HOME}

# Set shell with pipefail for proper error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create non-root user early to avoid ownership issues
RUN groupadd -r worker && useradd -r -g worker worker && \
    mkdir -p /home/worker && chown -R worker:worker /home/worker

# Install system dependencies (minimal for workers) with cache mounts
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && \
    apt-get --no-install-recommends install -y \
        build-essential \
        curl \
        gcc \
        libmagic-dev \
        libssl-dev \
        pkg-config

# Copy dependency files (including README.md like backend)
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml ${BUILD_CONTEXT_PATH}/uv.lock ./
# Create empty README.md if it doesn't exist in the copy
RUN touch README.md

# Copy local package dependencies to /unstract directory
# This provides the unstract packages for imports
COPY ${BUILD_PACKAGES_PATH}/ /unstract/

# Install external dependencies with --locked for FAST builds and cache mount
# No symlinks needed - PYTHONPATH handles the paths
# This layer is cached when dependencies don't change
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --group deploy --locked --no-install-project --no-dev

# Copy application code (this layer changes most frequently)
COPY ${BUILD_CONTEXT_PATH}/ ./

# Install project and OpenTelemetry instrumentation (as root to avoid permission issues) with cache mount
# No symlinks needed - PYTHONPATH handles the paths correctly
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --group deploy --locked && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement - && \
    { chmod +x ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true; } && \
    touch requirements.txt && \
    { chown -R worker:worker ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true; }

# Switch to worker user
USER worker

# Default command - runs the Docker-optimized worker script
ENTRYPOINT ["/app/run-worker-docker.sh"]
CMD ["general"]
