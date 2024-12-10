FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Set to immediately flush stdout and stderr streams without first buffering
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /unstract

ENV BUILD_CONTEXT_PATH prompt-service
ENV BUILD_PACKAGES_PATH unstract
ENV TARGET_PLUGINS_PATH src/unstract/prompt_service/plugins
ENV PDM_VERSION 2.16.1

RUN apt-get update; \
    apt-get --no-install-recommends install -y \
    # unstract sdk
    build-essential libmagic-dev pkg-config \
    # git url
    git; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    \
    pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}; \
    \
    # Creates a non-root user with an explicit UID and adds permission to access the /app folder
    # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
    adduser -u 5678 --disabled-password --gecos "" unstract;

USER unstract

WORKDIR /app

COPY --chown=unstract ${BUILD_CONTEXT_PATH} .
# Copy local dependency packages
COPY --chown=unstract ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=unstract ${BUILD_PACKAGES_PATH}/flags /unstract/flags

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
    #
    # Install plugins
    #
    for dir in "${TARGET_PLUGINS_PATH}"/*/; \
    do \
    # Remove trailing "/". \
    dirpath=${dir%*/}; \
    \
    # If no plugins, final part on split by "/" is equal to "*". \
    if [ "${dirpath##*/}" = "*" ]; then \
    continue; \
    fi; \
    \
    cd "$dirpath"; \
    echo "Installing plugin: ${dirpath##*/}..."; \
    \
    # PDM reuses active venv unless PDM_IGNORE_ACTIVE_VENV is set.
    pdm sync --prod --no-editable; \
    \
    cd -; \
    done; \
    #
    #
    #
    \
    # REF: https://docs.gunicorn.org/en/stable/deploy.html#using-virtualenv
    pip install --no-cache-dir gunicorn gevent; \
    \
    # Storage for prompt studio uploads
    mkdir prompt-studio-data;

EXPOSE 3003

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [ "./entrypoint.sh" ]
