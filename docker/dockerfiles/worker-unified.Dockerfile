# Unified Worker Dockerfile - Optimized for fast builds
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Unified Worker Container for All Worker Types" \
    version="${VERSION}"

# Set environment variables (CRITICAL: PYTHONPATH makes paths work!)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=workers \
    BUILD_PACKAGES_PATH=unstract \
    APP_HOME=/app

# Install system dependencies (minimal for workers)
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       curl \
       gcc \
       libmagic-dev \
       libssl-dev \
       pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

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

# Copy local package dependencies to the PARENT directory
# This makes ../unstract paths work!
COPY ${BUILD_PACKAGES_PATH}/ /unstract/

# Create symlink and install external dependencies with --locked for FAST builds
# The symlink makes the paths work without modification!
# Removed --group deploy since it's empty anyway
RUN ln -s /unstract /app/../unstract && \
    uv sync --locked --no-install-project --no-dev

# -----------------------------------------------
# FINAL STAGE - Minimal image for production
# -----------------------------------------------
FROM ext-dependencies AS production

# Copy application code (this layer changes most frequently)
COPY ${BUILD_CONTEXT_PATH}/ ./

# Ensure the symlink exists
RUN ln -sf /unstract /app/../unstract 2>/dev/null || true

# Install the application with --locked for FAST builds and setup
# Removed --group deploy since it's empty anyway
RUN uv sync --locked --no-dev && \
    chmod +x ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true && \
    touch requirements.txt

# Create non-root user for security
RUN groupadd -r worker && useradd -r -g worker worker && \
    chown -R worker:worker /app && \
    mkdir -p /home/worker && chown -R worker:worker /home/worker

# Switch to non-root user
USER worker

# Default command - runs the Docker-optimized worker script
ENTRYPOINT ["/app/run-worker-docker.sh"]
CMD ["general"]
