FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Set to immediately flush stdout and stderr streams without first buffering
ENV PYTHONUNBUFFERED 1

ENV BUILD_CONTEXT_PATH x2text-service
ENV PDM_VERSION 2.16.1

RUN apt-get update; \
    apt-get --no-install-recommends install -y \
        build-essential pkg-config && \
    pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}; \
    \
    # Creates a non-root user with an explicit UID and adds permission to access the /app folder
    # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
    adduser -u 5678 --disabled-password --gecos "" unstract;

USER unstract

WORKDIR /app

COPY --chown=unstract ${BUILD_CONTEXT_PATH} .

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
    # REF: https://docs.gunicorn.org/en/stable/deploy.html#using-virtualenv
    pip install --no-cache-dir gunicorn;

EXPOSE 3004

# During debugging, this entry point will be overridden.
# For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3004", "--timeout", "300", "run:app"]
