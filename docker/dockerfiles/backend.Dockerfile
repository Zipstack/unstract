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
    # Disable all telemetry by default
    OTEL_TRACES_EXPORTER=none \
    OTEL_TRACES_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_backend

# Install system dependencies
RUN apt-get update; \
    apt-get --no-install-recommends install -y \
    # unstract sdk
    build-essential libmagic-dev pkg-config \
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
    && uv run opentelemetry-bootstrap -a install

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
