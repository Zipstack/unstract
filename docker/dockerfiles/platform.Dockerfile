FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=platform-service \
    BUILD_PACKAGES_PATH=unstract \
    PDM_VERSION=2.16.1 \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_platform

# Install system dependencies
RUN apt-get update; \
    apt-get --no-install-recommends install -y  \
    # unstract sdk
    build-essential libmagic-dev; \
    \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    \
    pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}; \
    \
    # Creates a non-root user with an explicit UID and adds permission to access the /app folder
    # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
    adduser -u 5678 --disabled-password --gecos "" unstract;

USER unstract

WORKDIR /app

# Create venv and install gunicorn and other deps in it
RUN pdm venv create -w virtualenv --with-pip && \
    . .venv/bin/activate

# Read and execute access to non-root user to avoid security hotspot
# Write access to specific sub-directory need to be explicitly provided if required
COPY --chmod=755 ${BUILD_CONTEXT_PATH} /app/
# Copy local dependency packages
COPY --chown=unstract ${BUILD_PACKAGES_PATH} /unstract

# Install dependencies
RUN . .venv/bin/activate && \
    pdm sync --prod --no-editable --with deploy && \
    opentelemetry-bootstrap -a install

EXPOSE 3001

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3001", "--timeout", "300", "unstract.platform_service.run:app"]
