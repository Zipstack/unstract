# DOCKER BUILD
We can build the dockers locally using the below command

```
VERSION=test docker compose -f docker-compose.build.yaml build
```

Here `VERSION` env will be the docker tag version we need to use. For local testing we can pass any value. We can use the same compose files for building and publishing our dockers in our CI/CD systems as well.

If some one needs to build only one of the services they can do it by running build for that alone

Eg:-

```
VERSION=test docker compose -f docker-compose.build.yaml build frontend
```

# DOCKER RUN

NOTE: copy sample.*.env files into *.env and make required changes in it before running `docker compose up`

We can use the `docker compose up` command to run all the required services. Make sure build is done before the run and to use the same `VERSION`. 

```
VERSION=test docker compose -f docker-compose.yaml up -d
```

Now you should be able to access your frontend at http://frontend.unstract.localhost


# `src` FOLDER LAYOUT AND `gunicorn`

For the following project structure:

```bash
scheduler
  |- src
  |   |- unstract
  |       |- scheduler
  |           |- main.py
  |- pdm.lock
  |- pyproject.toml
```

Add the following in `pyproject.toml` to detect package in `src`:

```pyproject.toml
[tool.pdm.build]
includes = ["src"]
package-dir = "src"
```

This will install the project to:

```bash
.venv/lib/python3.12/site-packages/unstract/scheduler/main.py
```

This will allow `gunicorn` to refer the package directly as:

```bash
$ gunicorn "-c" "python:unstract.scheduler.config.gunicorn" "unstract.scheduler.main:app"
```
