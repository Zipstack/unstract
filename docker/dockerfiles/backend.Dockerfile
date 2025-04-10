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
    OTEL_TRACES_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_backend

# Install system dependencies
RUN apt-get update; \
    apt-get --no-install-recommends install -y \
    autoconf \
    automake \
    libtool \
    build-essential \
    cmake \
    ninja-build \
    pkg-config \
    python3-dev \
    # unstract sdk
    libmagic-dev freetds-dev libssl-dev libkrb5-dev gcc \
    g++ \
    # git url
    git; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*;

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy pyproject.toml and uv.lock file
COPY pyproject.toml /app
COPY uv.lock /app

COPY ${BUILD_CONTEXT_PATH}/ /app/
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/ /unstract

# Create virtual environment and install dependencies in one layer
RUN uv sync --frozen \
    && uv sync --group deploy \
    # Install opentelemetry for instrumentation
    && uv pip install --no-cache opentelemetry-distro \
    opentelemetry-exporter-otlp \
    && uv pip install --pre --no-binary :all: pymssql --no-cache --force-reinstall \
    && uv run opentelemetry-bootstrap -a install

# Install Python packages with specific flags
RUN uv pip uninstall numpy \
    && uv pip uninstall pandas scipy scikit-learn \
    && uv pip install --no-cache-dir --no-binary :all: numpy \
    && uv pip install --no-cache-dir pandas scipy scikit-learn

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
