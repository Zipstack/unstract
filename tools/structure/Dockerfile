FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."
ENV UNSTRACT_ENTRYPOINT "python /app/src/main.py"

# Install dependencies for SDK and prompt service
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg libsm6 libxext6 libmagic-dev poppler-utils \
        libreoffice freetds-dev freetds-bin \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -U pip
# Set the working directory in the container
WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install opentelemetry-distro opentelemetry-exporter-otlp && opentelemetry-bootstrap -a install
# Copy the contents of your project directory into the container at /app
COPY src /app/src/
WORKDIR /app/src


ENTRYPOINT ["python", "main.py"]
