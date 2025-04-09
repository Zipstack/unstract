# Use a specific version of Python slim image
FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc."
LABEL description="Runner Service Container"
LABEL version="1.0"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    # Set to immediately flush stdout and stderr streams without first buffering
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/unstract \
    BUILD_CONTEXT_PATH=runner \
    BUILD_PACKAGES_PATH=unstract \
    APP_HOME=/app

RUN apt-get update \
    && apt-get --no-install-recommends install -y docker git\
    && apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*


# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR ${APP_HOME}

# Copy only requirements files first to leverage Docker cache
COPY ${BUILD_CONTEXT_PATH}/pyproject.toml .
COPY ${BUILD_CONTEXT_PATH}/uv.lock .
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/core /unstract/core
COPY ${BUILD_PACKAGES_PATH}/flags /unstract/flags
COPY ${BUILD_CONTEXT_PATH} /app/

# Create virtual environment and install dependencies in one layer
RUN uv sync --frozen \
    && uv sync --group deploy \
    && uv pip install --no-cache opentelemetry-distro \
    opentelemetry-exporter-otlp \
    && uv run opentelemetry-bootstrap -a install


RUN \
    uv pip install --system; \
    \
    if [ -f cloud_requirements.txt ]; then \
    uv pip install --no-cache-dir -r cloud_requirements.txt; \
    else \
    echo "cloud_requirements.txt does not exist"; \
    fi

EXPOSE 5002

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
# The suggested maximum concurrent requests when using workers and threads is (2*CPU)+1
CMD [ "./entrypoint.sh" ]
