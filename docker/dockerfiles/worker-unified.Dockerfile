# Unified Worker Dockerfile - Optimized for fast builds
FROM python:3.12.9-slim AS base

LABEL maintainer="Zipstack Inc." \
    description="Unified Worker Container for All Worker Types"

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

# Create non-root user early to avoid ownership issues.
#
# UID/GID pinned to 999 EXPLICITLY. `useradd -r` without `-u` takes the next
# free system id descending from 999, which on this base (python:3.12.9-slim)
# is 999 today -- verified by running the same two commands in it -- so this
# pin changes nothing now. What it buys is determinism: a future base image
# that ships one more system user would silently shift this to 998, and any
# manifest or volume ownership assuming 999 would break on a rebuild with no
# code change.
#
# It is also what lets a pod set a numeric `runAsUser` at all. The sandbox
# worker (templates/worker-sandbox) does, so that `runAsNonRoot: true` does not
# have to depend on this Dockerfile keeping a `USER` line -- see the pod-level
# securityContext there.
RUN groupadd -r -g 999 worker && useradd -r -u 999 -g worker worker && \
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

# Increase timeout for large packages (flipt-client is ~45MB)
ENV UV_HTTP_TIMEOUT=120

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

# Install project, OpenTelemetry instrumentation, and executor plugins.
# No symlinks needed - PYTHONPATH handles the paths correctly.
# Executor plugins (cloud-only, no-op for OSS) register via setuptools entry points:
#   - unstract.executor.executors  (executor classes, e.g. table_extractor)
#   - unstract.executor.plugins    (utility plugins, e.g. highlight-data, challenge)
# Editable installs (-e) ensure Path(__file__) resolves to the source directory.
RUN uv sync --group deploy --locked && \
    uv run opentelemetry-bootstrap -a requirements | uv pip install --requirement - && \
    # Use OpenTelemetry v1 - v2 breaks LiteLLM with instrumentation enabled
    uv pip uninstall opentelemetry-instrumentation-openai-v2 && \
    uv pip install opentelemetry-instrumentation-openai && \
    { chmod +x ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true; } && \
    touch requirements.txt && \
    { chown -R worker:worker ./run-worker.sh ./run-worker-docker.sh 2>/dev/null || true; } && \
    for plugin_dir in /app/plugins/*/; do \
      if [ -f "$plugin_dir/pyproject.toml" ] && \
         grep -qE 'unstract\.executor\.(executors|plugins)' "$plugin_dir/pyproject.toml" 2>/dev/null; then \
        echo "Installing executor plugin: $(basename "$plugin_dir")" && \
        uv pip install -e "$plugin_dir" || true; \
      fi; \
    done

# Switch to the worker user BY NUMERIC ID (DL3066). Equivalent to `USER worker`
# now that the uid is pinned above, but it needs no /etc/passwd lookup and it is
# the id a pod's `runAsUser` has to match -- see
# templates/worker-sandbox/deployment.yaml in the cloud chart, which asserts 999.
USER 999


# Capture build version at the very end so it doesn't affect layer caching
ARG VERSION=dev
ENV UNSTRACT_APPS_VERSION=${VERSION}

# Default command - runs the Docker-optimized worker script
ENTRYPOINT ["/app/run-worker-docker.sh"]
CMD ["general"]
