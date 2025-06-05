# Unstract Runner

This module contains the logic for how Tools are executed in DND mode.

## Docker build and publish

Build docker image
```
docker build -t unstract/runner:1.1.1 .
```

Then publish it into Docker hub

```
docker push unstract/runner:1.1.1
```

## Run docker compose

To expose the Unstract runner service.

```
docker compose -f docker-compose.yaml up
```

## Using with Docker Desktop

The runner makes use of the python docker client's [from_env()](https://docker-py.readthedocs.io/en/stable/client.html#docker.client.from_env) to initialize the docker client. If you are using Docker Desktop, this might not work as expected due to the issue described [here](https://github.com/docker/docker-py/issues/3059). In that case follow the resolutions from the issue
- Either set `DOCKER_HOST` env to wherever the docker endpoint is configured.
```
export DOCKER_HOST=unix:///$HOME/.docker/desktop/docker.sock
```
- Or create the symlink manually (as recommended in the issue)
```
sudo ln -s "$HOME/.docker/run/docker.sock" /var/run/docker.sock
```

## Required Environment Variables

| Variable                   | Description                                                                                   |
| -------------------------- |-----------------------------------------------------------------------------------------------|
| `CELERY_BROKER_BASE_URL`   | Base URL for Celery's message broker, used to queue tasks. Must match backend configuration.       |
| `CELERY_BROKER_USER`       | Username for Celery's message broker.                                                         |
| `CELERY_BROKER_PASS`       | Password for Celery's message broker.                                                         |
| `TOOL_CONTAINER_NETWORK`   | Network used for running tool containers.                                                     |
| `TOOL_CONTAINER_LABELS`    | Labels applied to tool containers for observability [Optional].                               |
| `EXECUTION_DATA_DIR`       | Target mount directory within tool containers. (Default: "/data")                             |
| `LOG_LEVEL`                | Log level for runner (Options: INFO, WARNING, ERROR, DEBUG, etc.)                             |
| `REMOVE_CONTAINER_ON_EXIT`| Flag to decide whether to clean up/ remove the tool container after execution. (Default: True) |
