FROM python:3.9-slim

LABEL maintainer="Zipstack Inc."

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Set to immediately flush stdout and stderr streams without first buffering
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH /unstract

ENV BUILD_CONTEXT_PATH backend
ENV BUILD_PACKAGES_PATH unstract
ENV DJANGO_SETTINGS_MODULE "backend.settings.dev"
ENV PDM_VERSION 2.12.3

RUN apt-get update; \
    apt-get --no-install-recommends install -y \
        # unstract sdk
        build-essential libmagic-dev pandoc pkg-config tesseract-ocr \
        # git url
        git; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    \
    pip install --no-cache-dir -U pip pdm~=${PDM_VERSION};

WORKDIR /app

COPY ${BUILD_CONTEXT_PATH}/ .
# Copy local dependency packages
COPY ${BUILD_PACKAGES_PATH}/ /unstract

RUN set -e; \
    \
    rm -rf .venv .pdm* .python* requirements.txt 2>/dev/null; \
    \
    pdm venv create -w virtualenv --with-pip; \
    # source command may not be availble in sh
    . .venv/bin/activate; \
    \
    pdm sync --prod --no-editable; \
    \
    # REF: https://docs.gunicorn.org/en/stable/deploy.html#using-virtualenv
    pip install --no-cache-dir gunicorn;

EXPOSE 8000

ENTRYPOINT [ "./entrypoint.sh" ]
