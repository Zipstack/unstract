# Lightweight General Worker Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WORKER_TYPE=general

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
    CMD curl -f http://localhost:${METRICS_PORT:-8081}/health || exit 1

# Expose health check port
EXPOSE ${METRICS_PORT:-8081}

# Default command - can be overridden
CMD ["celery", "-A", "general", "worker", "--loglevel=info", "-Q", "celery", "--autoscale=4,1"]
