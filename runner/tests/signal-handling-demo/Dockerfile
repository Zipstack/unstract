# Signal Handling Test Container
# Replicates production environment for SIGTERM signal forwarding testing

FROM python:3.12.9-slim

LABEL maintainer="Unstract Team" \
      description="Signal Handling Test Container" \
      version="1.0"

# Set environment variables for proper Python output
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dumb-init (same as production tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends dumb-init && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy demo files
COPY shell-signal-test.py /app/

# Make scripts executable
RUN chmod +x /app/shell-signal-test.py
