FROM openjdk:8-jre-slim

LABEL maintainer="Zipstack Inc."

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE 1
# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

ENV BUILD_CONTEXT_PATH document-service
ENV PYTHON_VERSION 3.9
ENV PDM_VERSION 2.12.3

RUN DEBIAN_FRONTEND=noninteractive apt-get update; \
    apt-get --no-install-recommends install -y \
        fonts-dejavu fonts-dejavu-core fonts-dejavu-extra fonts-droid-fallback fonts-dustin \
        fonts-f500 fonts-fanwood fonts-freefont-ttf \
        fonts-liberation fonts-lmodern fonts-lyx \
        fonts-opensymbol fonts-sil-gentium fonts-texgyre fonts-tlwg-purisa \
        hyphen-af hyphen-en-us \
        libreoffice-common \
        python${PYTHON_VERSION} python3-pip \
        software-properties-common \
        unoconv; \
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*; \
    \
    pip install --no-cache-dir -U pip pdm~=${PDM_VERSION}; \
    \
    # Creates a non-root user with an explicit UID and adds permission to access the /app folder
    # For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
    adduser -u 5678 --disabled-password --gecos "" unstract;

USER unstract

WORKDIR /app

COPY --chown=unstract ${BUILD_CONTEXT_PATH}/ .

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
    pip install --no-cache-dir gunicorn; \
    \
    # Storage for document uploads and processing
    mkdir /app/uploads /app/processed;

EXPOSE 3002

# Wrapper to run both python server and libreoffice.
CMD [ "/app/wrapper.sh" ]
