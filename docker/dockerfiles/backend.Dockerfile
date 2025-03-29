FROM python:3.9-slim

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
    PDM_VERSION=2.16.1 \
    # OpenTelemetry configuration (disabled by default, enable in docker-compose)
    OTEL_TRACES_EXPORTER=none \
    OTEL_METRICS_EXPORTER=none \
    OTEL_LOGS_EXPORTER=none \
    OTEL_SERVICE_NAME=unstract_backend \
    # Enable specific instrumentations when tracing is enabled
    OTEL_PYTHON_CELERY_ENABLED=true \
    OTEL_PYTHON_DJANGO_ENABLED=true \
    OTEL_PYTHON_PSYCOPG2_ENABLED=true \
    OTEL_PYTHON_REDIS_ENABLED=true \
    OTEL_PYTHON_REQUESTS_ENABLED=true \
    OTEL_PYTHON_BOTO_ENABLED=true \
    OTEL_PYTHON_ASYNCIO_ENABLED=true \
    OTEL_PYTHON_HTTPX_ENABLED=true

# Install system dependencies
RUN apt-get update; \
    apt-get --no-install-recommends install -y \
        # unstract sdk
        build-essential libmagic-dev pkg-config \
        # git url
        git; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    \
    pip install --no-cache-dir -U pip pdm~=${PDM_VERSION};

WORKDIR /app

# Create venv and install gunicorn and other deps in it
RUN pdm venv create -w virtualenv --with-pip && \
    . .venv/bin/activate && \
    pip install --no-cache-dir \
        gunicorn

COPY ${BUILD_CONTEXT_PATH}/ /app/
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/ /unstract

# Install dependencies
RUN . .venv/bin/activate && \
    pdm sync --prod --no-editable && \
    opentelemetry-bootstrap -a install

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
