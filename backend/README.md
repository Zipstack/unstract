# Unstract Backend

Contains the backend services for Unstract written with Django and DRF.

## Dependencies

1. Postgres
1. Redis

## Getting started
**NOTE**: All commands are executed from `/backend` and require the venv to be active. Refer [these steps](/README.md#create-your-virtual-env) to create/activate your venv

### Install and run manually

- Ensure that you've sourced your virtual environment and installed dependencies mentioned [here](/README.md#create-your-virtual-env).

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

```
python manage.py migrate
python manage.py runserver localhost:8000
```

- Server will start and run at port 8000. (<http://localhost:8000>)

## Asynchronous execution/pipeline execution

 - Working with celery
 - Each pipeline or shared tasks will added to the queue (Redis), And the worker will consume from the queue

### Run Execution Worker

Run the following command to start the worker:

```bash
celery -A backend worker --loglevel=info
```

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
