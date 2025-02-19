FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=prompt-service \
    BUILD_PACKAGES_PATH=unstract \
    TARGET_PLUGINS_PATH=src/unstract/prompt_service/plugins \
    PDM_VERSION=2.16.1

# Install system dependencies
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

# Create venv and install gunicorn and other deps in it
RUN pdm venv create -w virtualenv --with-pip && \
    . .venv/bin/activate && \
    pip install --no-cache-dir \
        gunicorn \
        gevent \
        # Install opentelemetry for instrumentation
        opentelemetry-distro \
        opentelemetry-exporter-otlp && \
    opentelemetry-bootstrap -a install

# Read and execute access to non-root user to avoid security hotspot
# Write access to specific sub-directory need to be explicitly provided if required
COPY --chmod=755 ${BUILD_CONTEXT_PATH} /app/
# Copy local dependencies
COPY --chown=unstract ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY --chown=unstract ${BUILD_PACKAGES_PATH}/flags /unstract/flags

# Install dependencies and plugins (if any)
RUN . .venv/bin/activate && \
    pdm sync --prod --no-editable && \
    for dir in "${TARGET_PLUGINS_PATH}"/*/; do \
        dirpath=${dir%*/}; \
        if [ "${dirpath##*/}" != "*" ]; then \
            cd "$dirpath" && \
            echo "Installing plugin: ${dirpath##*/}..." && \
            pdm sync --prod --no-editable && \
            cd -; \
        fi; \
    done && \
    mkdir prompt-studio-data

EXPOSE 3003

# Default command
CMD ["./entrypoint.sh"]
