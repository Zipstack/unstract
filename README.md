# Unstract

[![pdm-managed](https://img.shields.io/badge/pdm-managed-blueviolet)](https://pdm-project.org)

TODO: Write few lines about the project.

## System Requirements

- `docker`
- `git`
- `pdm` (see below)
- `pyenv` (recommended to manage multiple Python versions)

## Quick Start

Install Docker Engine and the Docker Compose plugin on your workstation (see [instructions](https://docs.docker.com/engine/install/)).

Once Docker is installed, just run the `run-platform.sh` launch script.

The launch script does env setup with default values, builds Docker images, and finally runs them for you, to get you started in a few minutes. See usage examples below.

```bash
# Run entire Unstract platform with default env config.
./run-platform.sh

# Build and run docker containers with a specific version tag.
./run-platform.sh -v v0.1.0

# Display the help information.
./run-platform.sh -h

# Only do setup of environment files.
./run-platform.sh -e

# Only do docker images build with a specific version tag.
./run-platform.sh -b v0.1.0

### Build and run Docker containers in detached mode
./run-platform.sh -d -v v0.1.0
```

Now in your browser, visit [http://frontend.unstract.localhost](http://frontend.unstract.localhost).

That's all. Enjoy!

## Running with docker compose

- All services needed by the backend can be run with

```bash
cd docker/
VERSION=dev docker compose -f docker-compose.build.yaml build
VERSION=dev docker compose -f docker-compose.yaml up -d
```

Additional information on running with Docker can be found in [DOCKERISING.md](/DOCKERISING.md)

- Use the `-f` flag to run all dependencies necessary for development, this runs containers needed for testing as well such as Minio.

```bash
docker compose -f docker-compose-dev-essentials.yaml up
```

- It might take sometime on the first run to pull the images.

## Running locally

### Installation

- Install the below libraries which are needed to run Unstract
  - Linux

    ```bash
    sudo apt install build-essential pkg-config libpoppler-cpp-dev libmagic-dev python3-dev
    ```

  - Mac

    ```bash
    brew install pkg-config poppler freetds libmagic
    ```

### Create your virtual env

- In order to install dependencies and run a package, ensure that you've sourced a virtual environment within that package. All commands in this repository assumes that you have sourced your required venv.

```bash
cd <service>

# Create venv
pdm venv create -w virtualenv --with-pip
eval "$(pdm venv activate in-project)"

# Remove venv
eval "$(pdm venv activate in-project)"
```


### Install dependencies with PDM

- This repository makes use of [PDM](https://github.com/pdm-project/pdm) for managing dependencies with the help of a virtual
environment.
- If you haven't installed PDM in your machine yet, 
  - Install it using the below command
  ```
  curl -sSL https://pdm.fming.dev/install-pdm.py | python3 -
  ```
  - Or install it from PyPI using `pip`
  ```
  pip install pdm
  ```

Ensure you're running the PDM commands from the corresponding package root
- Install dependencies for running the package with

```
pdm install
```
This install dev dependencies as well by default
- For production, install the requirements with

```
pdm install --prod
```

- With PDM its possible to run some services from any directory within this
repository. To list the possible scripts that can be executed
```
pdm run -l
```

- Add a new dependency with (ensure you're running it from the correct project's root)
Perform an editable install with `-e` only for local development.
```
pdm add <package_from_PyPI>
pdm add -e <relative_path_to_local_package>
```
- List all dependencies with
```
pdm list
```
- After updating `pyproject.toml`s with a newly added dependency, the lock file can be updated with
```
pdm lock
```
- Refer [PDM's documentation](https://pdm.fming.dev/latest/reference/cli/) for further details.

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

- Check [backend/README.md](/backend/README.md) for running the backend.

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
