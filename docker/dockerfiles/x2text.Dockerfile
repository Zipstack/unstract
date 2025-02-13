FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

ENV \
    # Keeps Python from generating .pyc files in the container
    PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    BUILD_CONTEXT_PATH=x2text-service \
    PDM_VERSION=2.16.1

RUN pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}; \
    \
    # Creates a non-root user with an explicit UID and adds permission to access the /app folder
    # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
    adduser -u 5678 --disabled-password --gecos "" unstract;

USER unstract

WORKDIR /app

# Create venv and install gunicorn and other deps in it
RUN pdm venv create -w virtualenv --with-pip && \
    . .venv/bin/activate && \
    pip install --no-cache-dir gunicorn \
    opentelemetry-distro opentelemetry-exporter-otlp && \
    opentelemetry-bootstrap -a install

# Read and execute access to non-root user to avoid security hotspot
# Write access to specific sub-directory need to be explicitly provided if required
COPY --chmod=755 ${BUILD_CONTEXT_PATH} /app/

# Install dependencies
RUN . .venv/bin/activate && \
    pdm sync --prod --no-editable

EXPOSE 3004

# During debugging, this entry point will be overridden.
# For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD [".venv/bin/gunicorn", "--bind", "0.0.0.0:3004", "--timeout", "300", "run:app"]
