# Use a specific version of Python slim image
FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc."
LABEL description="Prompt Service Container"
LABEL version="1.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
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

# Install system dependencies
RUN apt-get update; \
    apt-get --no-install-recommends install -y \
    # unstract sdk
    build-essential libmagic-dev pkg-config \
    # git url
    git; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    # Creates a non-root user with an explicit UID and adds permission to access the /app folder
    # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
    adduser -u 5678 --disabled-password --gecos "" ${APP_USER};

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR ${APP_HOME}

# Create app directory and set permissions
RUN mkdir -p ${APP_HOME} \
    && chown -R ${APP_USER}:${APP_USER} ${APP_HOME}

# Copy only requirements files first to leverage Docker cache
COPY --chown=unstract ${BUILD_CONTEXT_PATH}/pyproject.toml .
COPY --chown=unstract ${BUILD_CONTEXT_PATH}/uv.lock .
# Copy local dependencies
COPY --chown=unstract ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=unstract ${BUILD_PACKAGES_PATH}/flags /unstract/flags
# TODO: Security issue but ignoring it for nuitka based builds
COPY --chown=unstract ${BUILD_CONTEXT_PATH} /app/
# Switch to non-root user
USER ${APP_USER}

# Create virtual environment and install dependencies in one layer
RUN uv sync --frozen \
    && uv sync --group deploy \
    && uv pip install --no-cache opentelemetry-distro \
    opentelemetry-exporter-otlp \
    && uv run opentelemetry-bootstrap -a install

# Install dependencies and plugins (if any)
RUN . .venv/bin/activate && \
    uv sync && \
    for dir in "${TARGET_PLUGINS_PATH}"/*/; do \
    dirpath=${dir%*/}; \
    if [ "${dirpath##*/}" != "*" ]; then \
    cd "$dirpath" && \
    echo "Installing plugin: ${dirpath##*/}..." && \
    uv sync && \
    cd -; \
    fi; \
    done && \
    mkdir prompt-studio-data


RUN uv sync --group deploy

EXPOSE 3003

# Default command
CMD ["./entrypoint.sh"]
