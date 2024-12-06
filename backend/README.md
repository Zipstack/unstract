# Unstract Backend

Contains the backend services for Unstract written with Django and DRF.

## Dependencies

1. Postgres
1. Redis

## Getting started

### Install and run locally

#### Create your virtual env

All commands assumes that you have activated your `venv`.

```bash
# Create venv
pdm venv create -w virtualenv --with-pip
eval "$(pdm venv activate in-project)"

# Remove venv
pdm venv remove in-project
```

#### Installing dependencies

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

#### Running commands

- If you plan to run the django server locally, make sure the dependent services are up (either locally or through docker compose)
- Copy `sample.env` into `.env` and update the necessary variables. For eg:

```
DJANGO_SETTINGS_MODULE='backend.settings.dev'
DB_HOST='localhost'
DB_USER='unstract_dev'
DB_PASSWORD='unstract_pass'
DB_NAME='unstract_db'
DB_PORT=5432
```

- If you've made changes to the model, run `python manage.py makemigrations`, else ignore this step
- Run the following to apply any migrations to the DB and start the server

```bash
python manage.py migrate
python manage.py runserver localhost:8000
```

- Server will start and run at port 8000. (<http://localhost:8000>)
  
## Authentication

The default username is `unstract` and the default password is `unstract`.

### Initial Setup

To customize the username or password:

1. Navigate to `/backend/.env` created from [/backend/sample.env](/backend/sample.env)
2. Update the values for `DEFAULT_AUTH_USERNAME` and `DEFAULT_AUTH_PASSWORD` with strong, unique credentials of your choosing
3. Save the `/backend/.env` file and restart the server to apply changes

### Updating Credentials

To update the username or password after initial setup:

1. Modify the credentials in `/backend/.env`
    - **DEFAULT_AUTH_USERNAME**=`your_new_username`
    - **DEFAULT_AUTH_PASSWORD**=`your_new_password`
2. Save changes and restart `backend` service

Now you can login with the new credentials.

### Important Notes

- **DEFAULT_AUTH_USERNAME** must not match the `username` of any `Django superuser` or `admin` account. Keeping them distinct ensures security and avoids potential conflicts.
- Use strong and unique credentials to protect your system.
- The authentication system validates credentials against the values specified in the `/backend/.env` file.

## Asynchronous Execution

This project uses Celery for handling asynchronous execution. Celery tasks are managed through various queues and consumed by workers.

> ETL, TASK, and API Deployment tasks are handled by these asynchronous workers. Log management also utilizes Celery.

### Queues

| Queue Name                 | Description                                    | Tasks                                                 |
|----------------------------|------------------------------------------------|-------------------------------------------------------|
| `celery`                   | Default queue for general Celery tasks, including those without a specific queue. | Webhook notifications, Pipeline (ETL, Tasks) Executions. |
| `celery_periodic_logs`     | Queue for persisting logs into the database.   |                                                       |
| `celery_log_task_queue`    | Queue for publishing logs to WebSocket clients. |                                                       |
| `celery_api_deployments`   | Queue for managing API deployment tasks.       |                                                       |

### Run Execution Worker

To start a Celery worker, use the following command:

```bash
celery -A backend worker --loglevel=info -Q <queue_name>
```

### Autoscaling Workers
```bash
  celery -A backend worker --loglevel=info -Q <queue_name> --autoscale=<max_workers>,<min_workers>
```

Celery supports autoscaling of worker processes, allowing you to dynamically adjust the number of workers based on workload.

- **Max Workers (`max_workers`)**: This value is related to your CPU resources and the level of concurrency you need.
  - For CPU-bound tasks: Consider setting `max_workers` close to or slightly above the number of CPU cores.
  - For I/O-bound tasks: You can set a higher `max_workers` value, typically 2-3 times the number of CPU cores.

- **Min Workers (`min_workers`)**: This is the minimum number of worker processes that will always be running.


### Worker Dashboard

- We have to ensure the package flower is installed in the current environment
- Run command

```bash
celery -A backend flower
```
This command will start Flower on the default port (5555) and can be accessed via a web browser. Flower provides a user-friendly interface for monitoring and managing Celery tasks


## Connecting to Postgres

Follow the below steps to connect to the postgres DB running with `docker compose`.

1. Exec into a shell within the postgres container

```
docker compose exec -it db bash
```

2. Connect to the db as the specified user

```
psql -d unstract_db -U unstract_dev
```

3. Execute PSQL commands within the shell.

## API Docs

While running the backend server locally, access the API documentation that's auto generated at
the backend endpoint `/api/v1/doc/`.

**NOTE:** There exists issues accessing this when the django server is run with gunicorn (in case of running with
a container)

- [Account](account/api_doc.md)
- [FileManagement](file_management/api_doc.md)

## Connectors

### Google Drive
The Google Drive connector makes use of [PyDrive2](https://pypi.org/project/PyDrive2/) library and supports only OAuth 2.0 authentication.
To set it up, follow the first step higlighted in [Google's docs](https://developers.google.com/identity/protocols/oauth2#1.-obtain-oauth-2.0-credentials-from-the-dynamic_data.setvar.console_name-.) and set the client ID and client secret
as envs in `backend/.env`
```
GOOGLE_OAUTH2_KEY="<client-id>"
GOOGLE_OAUTH2_SECRET="<client-secret>"
```

## Tool Registry

Information regarding how tools are added and maintained can be found [here](/unstract/tool-registry/README.md).


# Archived - (EXPERIMENTAL)

## Accessing the admin site

- If its the first time, create a super user and follow the on-screen instructions

```
python manage.py createsuperuser
```

- Register your models in `<app>/admin.py`, for example

```
from django.contrib import admin
from .models import Prompt

admin.site.register(Prompt)
```

- Make sure the server is running and hit the `/admin` endpoint

## Running unit tests

Units tests are run with [pytest](https://docs.pytest.org/en/7.3.x/) and [pytest-django](https://pytest-django.readthedocs.io/en/latest/index.html)

```
pytest
pytest prompt # To run for an app named prompt
```

All tests are organized within an app, for eg: `prompt/tests/test_urls.py`

**NOTE:** The django server need not be up to run the tests, however the DB needs to be running.
