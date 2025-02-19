FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=runner \
    BUILD_PACKAGES_PATH=unstract \
    PDM_VERSION=2.16.1

RUN apt-get update \
    && apt-get --no-install-recommends install -y docker \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/* \
    \
    && pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}

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

COPY ${BUILD_CONTEXT_PATH} /app/
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY ${BUILD_PACKAGES_PATH}/flags /unstract/flags

RUN \
    # source command may not be availble in sh
    . .venv/bin/activate; \
    \
    pdm sync --prod --no-editable; \
    \
    if [ -f cloud_requirements.txt ]; then \
        pip install --no-cache-dir -r cloud_requirements.txt; \
    else \
        echo "cloud_requirements.txt does not exist"; \
    fi

EXPOSE 5002

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
# The suggested maximum concurrent requests when using workers and threads is (2*CPU)+1
CMD [ "./entrypoint.sh" ]
