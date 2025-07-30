FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc." \
      description="Structure Tool Container" \
      version="1.0"

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    APP_HOME=/app \
    # OpenTelemetry configuration
    OTEL_SERVICE_NAME="structure-tool" \
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    # Enable context propagation
    OTEL_PROPAGATORS="tracecontext"

# Install system dependencies in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg libsm6 libxext6 libmagic-dev poppler-utils \
    libreoffice freetds-dev freetds-bin && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Set the working directory in the container
WORKDIR ${APP_HOME}

# Copy only requirements file first for better caching
COPY requirements.txt ${APP_HOME}/

# Install OpenTelemetry packages first (less likely to change)
RUN uv pip install --system \
    opentelemetry-distro \
    opentelemetry-exporter-otlp \
    platformdirs>=3.0.0

# Set shell options for better error handling
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install project dependencies separately from OpenTelemetry
# This allows for better caching when only project dependencies change
RUN uv pip install --system -r requirements.txt && \
    opentelemetry-bootstrap -a requirements | uv pip install --system --requirement -

# Copy the source code after installing all dependencies
# This ensures that changes to the source code don't invalidate the dependency layers
COPY src ${APP_HOME}/src/
WORKDIR ${APP_HOME}/src

ENTRYPOINT ["opentelemetry-instrument", "python", "main.py"]
