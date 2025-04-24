FROM python:3.12.9-slim

LABEL maintainer="Zipstack Inc."


# Install dependencies for unstructured library's partition
RUN apt-get update && apt-get --no-install-recommends -y install libmagic-dev poppler-utils\
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U pip
# Set the working directory in the container
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir \
    opentelemetry-distro \
    opentelemetry-exporter-otlp \
    platformdirs>=3.0.0 \
    && opentelemetry-bootstrap -a install
# Copy the contents of your project directory into the container at /app
COPY src /app/src/
WORKDIR /app/src


ENTRYPOINT ["opentelemetry-instrument","python", "main.py"]
