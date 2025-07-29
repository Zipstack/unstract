# Base image for all workers with common dependencies
# This image can be built once and reused by all workers
FROM python:3.12.9-slim AS base

ARG VERSION=dev
LABEL maintainer="Zipstack Inc." \
    description="Base Worker Image with Common Dependencies" \
    version="${VERSION}"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    APP_HOME=/app

# Install system dependencies
RUN apt-get update \
    && apt-get --no-install-recommends install -y \
       curl \
       gcc \
       libmagic-dev \
       git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Create working directory
WORKDIR ${APP_HOME}

# -----------------------------------------------
# COMMON DEPENDENCIES STAGE
# -----------------------------------------------
FROM base AS common-deps

# Copy shared dependency files
COPY workers/shared/pyproject.toml /app/workers/shared/
COPY workers/pyproject.toml /app/workers/

# Install common shared dependencies
WORKDIR /app/workers/shared
RUN uv sync --locked --no-install-project --no-dev

# This image can be used as base for all worker images
WORKDIR ${APP_HOME}
