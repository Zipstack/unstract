FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc."

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=backend \
    BUILD_PACKAGES_PATH=unstract \
    DJANGO_SETTINGS_MODULE="backend.settings.dev" \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_backend

# Install system dependencies
RUN apt-get update && \
    apt-get --no-install-recommends install -y \
    autoconf \
    automake \
    build-essential \
    cmake \
    freetds-dev \
    g++ \
    gcc \
    git \
    libkrb5-dev \
    libmagic-dev \
    libssl-dev \
    libtool \
    ninja-build \
    pkg-config \
    python3-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy only what's needed for dependency installation first
COPY pyproject.toml uv.lock /app/

# Copy source code and dependencies
COPY ${BUILD_CONTEXT_PATH}/ /app/
COPY ${BUILD_PACKAGES_PATH}/ /unstract/

# Install dependencies in one layer
RUN uv sync --frozen && \
    uv sync --group deploy && \
    .venv/bin/python3 -m ensurepip --upgrade && \
    uv run opentelemetry-bootstrap -a install && \
    # Scientific packages reinstallation
    # uv pip install --pre --no-binary :all: pymssql --no-cache --force-reinstall && \
    uv pip uninstall numpy pandas scipy scikit-learn && \
    uv pip install --no-cache-dir --no-binary :all: numpy && \
    uv pip install --no-cache-dir pandas scipy scikit-learn

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
