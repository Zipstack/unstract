# Task Backend Worker - Production Dockerfile
FROM python:3.12-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user
RUN groupadd -r taskworker && useradd -r -g taskworker taskworker

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy task-abstraction library
COPY unstract/task-abstraction/src /app/task-abstraction/src
ENV PYTHONPATH="/app/task-abstraction/src:$PYTHONPATH"

# Copy task-backend service
COPY task-backend/src /app/src
COPY task-backend/pyproject.toml /app/

# Install task-backend in editable mode
RUN pip install -e .

# Create directories for logs and data
RUN mkdir -p /app/logs /app/data \
    && chown -R taskworker:taskworker /app

# Switch to non-root user
USER taskworker

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -m unstract.task_backend.cli.main --health-check

# Default command
CMD ["python", "-m", "unstract.task_backend.cli.main"]