FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Set to immediately flush stdout and stderr streams without first buffering
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /unstract

ENV BUILD_CONTEXT_PATH worker
ENV BUILD_PACKAGES_PATH unstract
ENV PDM_VERSION 2.16.1

RUN apt-get update \
    && apt-get --no-install-recommends install -y docker build-essential pkg-config  freetds-dev libssl-dev libkrb5-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
    \
    && pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}

WORKDIR /app

COPY ${BUILD_CONTEXT_PATH} .
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/core /unstract/core

RUN set -e; \
    \
    rm -rf .venv .pdm* .python* requirements.txt 2>/dev/null; \
    \
    pdm venv create -w virtualenv --with-pip; \
    # source command may not be availble in sh
    . .venv/bin/activate; \
    \
    # Install opentelemetry for instrumentation.
    pip install opentelemetry-distro opentelemetry-exporter-otlp; \
    \
    opentelemetry-bootstrap -a install; \
    \
    pdm sync --prod --no-editable; \
    \
    [ -f cloud_requirements.txt ] && pip install -r cloud_requirements.txt || { echo "cloud_requirements.txt does not exist";}; \
    \
    # REF: https://docs.gunicorn.org/en/stable/deploy.html#using-virtualenv
    pip install --no-cache-dir gunicorn gevent;

EXPOSE 5002

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
# The suggested maximum concurrent requests when using workers and threads is (2*CPU)+1
CMD [ "./entrypoint.sh" ]
