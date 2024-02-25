# Unstract Worker 

This module contains the logic for how Tools are executed in DND mode.

## Docker build and publish

Build docker image
```
docker build -t unstract/worker:1.1.1 .
```

Then publish it into Docker hub

```
docker push unstract/worker:1.1.1   
```

## Run docker compose

To expose the Unstract worker service.

```
docker compose -f docker-compose.yaml up
```

## Using with Docker Desktop

The worker makes use of the python docker client's [from_env()](https://docker-py.readthedocs.io/en/stable/client.html#docker.client.from_env) to initialize the docker client. If you are using Docker Desktop, this might not work as expected due to the issue described [here](https://github.com/docker/docker-py/issues/3059). In that case follow the resolutions from the issue
- Either set `DOCKER_HOST` env to wherever the docker endpoint is configured.
```
export DOCKER_HOST=unix:///$HOME/.docker/desktop/docker.sock
```
- Or create the symlink manually (as recommended in the issue)
```
sudo ln -s "$HOME/.docker/run/docker.sock" /var/run/docker.sock
```
