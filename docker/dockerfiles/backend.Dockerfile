FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Set to immediately flush stdout and stderr streams without first buffering
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /unstract

ENV BUILD_CONTEXT_PATH backend
ENV BUILD_PACKAGES_PATH unstract
ENV DJANGO_SETTINGS_MODULE "backend.settings.dev"
ENV UV_VERSION 0.6.0

# Disable all telemetry by default
ENV OTEL_TRACES_EXPORTER none
ENV OTEL_METRICS_EXPORTER none
ENV OTEL_LOGS_EXPORTER none
ENV OTEL_SERVICE_NAME unstract_backend

RUN apt-get update; \
    apt-get --no-install-recommends install -y \
        # unstract sdk
        build-essential libmagic-dev pkg-config \
        # git url
        git; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    \
    pip install --no-cache-dir -U pip uv~=${UV_VERSION};

WORKDIR /app

COPY ${BUILD_CONTEXT_PATH}/ .
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/ /unstract

RUN set -e; \
    \
    rm -rf .venv .pdm* .python* 2>/dev/null; \
    \
    uv venv; \
    # source command may not be availble in sh
    . .venv/bin/activate; \
    \
    # Install opentelemetry for instrumentation.
    pip install opentelemetry-distro opentelemetry-exporter-otlp; \
    \
    opentelemetry-bootstrap -a install; \
    \
    # Application dependencies.
    uv sync --no-dev --no-editable --locked; \
    \
    # REF: https://docs.gunicorn.org/en/stable/deploy.html#using-virtualenv
    uv pip install --no-cache-dir gunicorn;

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
