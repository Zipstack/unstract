### Platform Service

Platform service is a REST API interface for the SDK to talk to the platform.

#### Prerequisites

- Uploads directory to be created. `/tmp/platform_service/uploads` Note that this can be changed using the environment
  variables. The variable to change is `UPLOAD_FOLDER`.
- Postgres server with `pg_vector` extension installed
- Databases `unstract` and `unstract_vectors` must be available in Postgres

#### Environment Variables

This service requires a few environment variables to be set. Take a look at `sample.env`. Make a copy of this file and
name it as `.env`. Then fill in the values for the variables. The `.env` file automatically gets loaded when the service
is started.

#### Running the service

Setup a virtual environment and install the requirements:

```commandline
uv venv
```

Once a virtual environment is created or if you already have created one, activate it:

```commandline
source .venv/bin/activate
```

Install the dependencies needed to run the service
```commandline
uv sync
```

To run the service locally (make sure the `.env` file is present):

```commandline
flask run --host localhost --port 3001
```

> Note that this is for debugging purposes only. Please follow the good practices for running a Flash application in
> production
