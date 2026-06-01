# Document Classifier Tool

The document classifier tool classifies documents and copies them to a folder based on the classification.

## Required environment variables

| Variable                   | Description                                                           |
| -------------------------- |-----------------------------------------------------------------------|
| `PLATFORM_SERVICE_HOST`    | The host in which the platform service is running                     |
| `PLATFORM_SERVICE_PORT`    | The port in which the service is listening                            |
| `PLATFORM_SERVICE_API_KEY` | The API key for the platform                                          |
| `EXECUTION_DATA_DIR`       | The directory in the filesystem which has contents for tool execution |

## Testing the tool locally

### Setting up a dev environment

Setup a virtual environment and activate it

```commandline
python -m venv .venv
source .venv/bin/activate
```

Install the dependencies for the tool

```commandline
pip install -r requirements.txt
```

To use the local development version of the [unstract-sdk](https://pypi.org/project/unstract-sdk/) install it from the local repository.
Replace the path with the path to your local repository

```commandline
pip install -e ~/path_to_repo/sdks/.
```

### Tool execution preparation

Load the environment variables for the tool.
Make a copy of the `sample.env` file and name it `.env`. Fill in the required values.
They get loaded with [python-dotenv](https://pypi.org/project/python-dotenv/) through the SDK.

Update the tool's `data_dir` marked by the `EXECUTION_DATA_DIR` env. This has to be done before each tool execution since the tool updates the `INFILE` and `METADATA.json`.

### Run SPEC command

Represents the JSON schema for the runtime configurable `settings` of a tool

```commandline
python main.py --command SPEC
```

### Run PROPERTIES command

Describes some metadata for the tool such as its `version`, `description`, `inputs` and `outputs`

```commandline
python main.py --command PROPERTIES
```

### Run ICON command

Returns the SVG icon for the tool, used by Unstract's frontend

```commandline
python main.py --command ICON
```

### Run VARIABLES command

Represents the runtime variables or envs that will be used by the tool

```commandline
python main.py --command VARIABLES
```

### Run RUN command

The schema of the JSON required for settings can be found by running the [SPEC](#run-spec-command) command. Alternatively if you have access to the code base, it is located in the `config` folder as `spec.json`.

```commandline
python main.py \
    --command RUN \
    --settings '{
        "llmAdapterId": "e9884c72-3920-43e7-9904-bb59f308f50d",
        "classificationBins": ["business", "sports", "politics", "entertainment", "tech"],
        "useCache": true
    }' \
    --log-level DEBUG

```

## Testing the tool from its docker image

Build the tool docker image from the folder containing the `Dockerfile` with

```commandline
docker build -t unstract/tool-classifier:0.0.1 .
```

Make sure the directory pointed by `EXECUTION_DATA_DIR` has the required information for the tool to run and
necessary services like the `platform-service` is up.
To test the tool from its docker image, run the following command

```commandline
docker run -it \
    --network unstract-network \
    --env-file .env \
    -v "$(pwd)"/data_dir:/app/data_dir \
    unstract/tool-classifier:0.0.1 \
    --command RUN \
    --settings '{
        "llmAdapterId": "e9884c72-3920-43e7-9904-bb59f308f50d",
        "classificationBins": ["business", "sports", "politics", "entertainment", "tech"],
        "useCache": true
    }' \
    --log-level DEBUG

```
