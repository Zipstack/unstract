# Lightweight Callback Worker Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WORKER_TYPE=callback

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN groupadd -r celery && useradd -r -g celery celery
RUN chown -R celery:celery /app
USER celery

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${METRICS_PORT:-8083}/health || exit 1

# Expose health check port
EXPOSE ${METRICS_PORT:-8083}

# Default command - can be overridden
CMD ["celery", "-A", "file_processing_callback_lite", "worker", "--loglevel=info", "-Q", "file_processing_callback,api_file_processing_callback", "--autoscale=4,1"]
