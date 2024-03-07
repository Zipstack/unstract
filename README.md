# Unstract

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm-project.org)

Use LLMs to eliminate manual processes involving unstructured data.

## System Requirements

- `docker` (see [instructions](https://docs.docker.com/engine/install/))
- `git`
- `pdm` (see below)
- `pyenv` (recommended to manage multiple Python versions)

## Quick Start

Just run the `run-platform.sh` launch script to get started in few minutes.

The launch script does env setup with default values, pulls public docker images or builds them locally and finally runs them in containers.

```bash
# Pull and run entire Unstract platform with default env config.
./run-platform.sh

# Pull and run docker containers with a specific version tag.
./run-platform.sh -v v0.1.0

# Build docker images locally and run with a specific version tag.
./run-platform.sh -b -v v0.1.0

# Display the help information.
./run-platform.sh -h

# Only do setup of environment files.
./run-platform.sh -e

# Only do docker images pull with a specific version tag.
./run-platform.sh -p -v v0.1.0

# Only do docker images pull by building locally with a specific version tag.
./run-platform.sh -p -b -v v0.1.0

# Pull and run docker containers in detached mode.
./run-platform.sh -d -v v0.1.0
```

Now visit [http://frontend.unstract.localhost](http://frontend.unstract.localhost) in your browser.

That's all. Enjoy!

## Running with docker compose

See [Docker README.md](docker/README.md).

## Running locally

### Installation

- Install the below libraries which are needed to run Unstract
  - Linux

    ```bash
    apt install build-essential libmagic-dev pandoc pkg-config tesseract-ocr
    ```

  - Mac

    ```bash
    brew install freetds libmagic pkg-config poppler
    ```

### Create your virtual env

All commands assumes that you have activated your `venv`.

```bash
cd <service>

# Create venv
pdm venv create -w virtualenv --with-pip
eval "$(pdm venv activate in-project)"

# Remove venv
pdm venv remove in-project
```


### Install dependencies with PDM

[PDM](https://github.com/pdm-project/pdm) is used for dependency management.

```bash
# Install via script
curl -sSL https://pdm.fming.dev/install-pdm.py | python3 -

# Install via pip
pip install pdm
```

Go to service dir and install dependencies listed in corresponding `pyproject.toml`.

```bash
# Install dependencies
pdm install

# Install specific dev dependency group
pdm install --dev -G lint

# Install production dependencies only
pdm install --prod --no-editable
```

PDM allows you to run scripts applicable within the service dir.

```bash
# List the possible scripts that can be executed
pdm run -l
```

Add dependencies as follows.

```bash
# Add a new service dependency to ts pyproject.toml.
pdm add <package_from_PyPI>
# Add a relative path as an editable install.
pdm add -e <relative_path_to_local_package>
# List all dependencies.
pdm list
```

After modifying `pyproject.toml`, the lock file can be updated as below.

```
pdm lock
```

See [PDM's documentation](https://pdm.fming.dev/latest/reference/cli/) for further details.

### Configuring Postgres

- Create a Postgres user and DB for the BE and configure it like so

```
POSTGRES_USER: unstract_dev
POSTGRES_PASSWORD: unstract_pass
POSTGRES_DB: unstract_db
```

If you require a different config, make sure the necessary envs from [backend/sample.env](/backend/sample.env) are exported.

### Pre-commit hooks

- We use pre-commit to run some hooks whenever code is pushed to perform linting and static code analysis among other checks.
- Ensure dev dependencies are installed and you're in the virtual env
- Install hooks with `pre-commit install` or `pdm run pre-commit install`
- Manually trigger pre-commit hooks in following ways:
  ```bash
  #
  # Using the tool directly
  #
  # Run all pre-commit hooks
  pre-commit run
  # Run specific pre-commit hook
  pre-commit run flake8
  # Run mypy pre-commit hook for selected folder
  pre-commit run mypy --files prompt-service/**/*.py
  # Run mypy for selected folder
  mypy prompt-service/**/*.py

  #
  # Using pdm to run the scripts
  #
  # Run all pre-commit hooks
  pdm run pre-commit run
  # Run specific pre-commit hook
  pdm run pre-commit run flake8
  # Run mypy pre-commit hook for selected folder
  pdm run pre-commit run mypy --files prompt-service/**/*.py
  # Run mypy for selected folder
  pdm run mypy prompt-service/**/*.py
  ```

### Backend

- Check [backend/README.md](backend/README.md) for running the backend.

### Frontend

- Install dependencies with `npm install`
- Start the server with `npm start`

### Traefik Proxy Overrides for Local + Docker Runs

It is possible to simultaneously run few services directly on docker host while others are run as docker containers via docker compose.  
This enables seamless development without worrying about deployment of other services which you are not concerned with.

We just need to override default Traefik proxy routing to allow this, that's all.

1. Copy `docker/sample.proxy_overrides.yaml` to `docker/proxy_overrides.yaml`.  
   Modify to update Traefik proxy routes for services running directly on docker host (`host.docker.internal:<port>`).

2. Update host name of dependency components in config of services running directly on docker host:
    - Replace as `*.localhost` IF container port is exposed on docker host
    - **OR** use container IPs obtained via `docker network inspect unstract-network`
    - **OR** run `dockers/scripts/resolve_container_svc_from_host.sh` IF container port is NOT exposed on docker host or if you want to keep dependency host names unchanged

Run the services.

#### Generate Encryption key to be used in backend and Platform service

 Generate Fernet Key Refer https://pypi.org/project/cryptography/
 
 `ENCRYPTION_KEY=$(python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())")`

 use the above generated encryption, key in ENV's of platform and backend

#### Conflicting Host Names

When same host name environment variables are used by both the service running locally and a service
running in a container (for example, running in from a tool), host name resolution conflicts can arise for the following:

- `localhost` -> Using this inside a container points to the container itself, and not the host.
- `host.docker.internal` -> Meant to be used inside containers only, to get host IP.
Does not make sense to use in services running locally.

*In such cases, use another host name and point the same to host IP in `/etc/hosts`.*

For example, the backend uses the PROMPT_HOST environment variable, which is also supplied
in the Tool configuration when spawning Tool containers. If the backend is running
locally and the Tools are in containers, we could set the value to
`prompt-service` and add it to `/etc/hosts` as shown below.
```
<host_local_ip>    prompt-service
```
