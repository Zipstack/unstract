FROM python:3.12-slim-trixie

LABEL maintainer="Zipstack Inc."

ENV \
    # Extended PYTHONPATH to include all unstract module source directories
    APP_HOME=/app \
    BUILD_PACKAGES_PATH=unstract

# Install dependencies for unstructured library's partition
RUN apt-get update && apt-get --no-install-recommends -y install dumb-init libmagic-dev poppler-utils\
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U pip
# Set the working directory in the container
WORKDIR ${APP_HOME}
COPY tools/text_extractor/requirements.txt /app/

# Copy specific subdirectories while preserving structure
COPY ${BUILD_PACKAGES_PATH}/sdk1 /unstract/sdk1
COPY ${BUILD_PACKAGES_PATH}/flags /unstract/flags

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
    opentelemetry-distro \
    opentelemetry-exporter-otlp \
    platformdirs>=3.0.0 \
    && opentelemetry-bootstrap -a install


# Copy the contents of your project directory into the container at /app
COPY tools/text_extractor/src /app/src/
WORKDIR /app/src


ENTRYPOINT ["opentelemetry-instrument", "python", "main.py"]
