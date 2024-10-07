# Text Extractor Tool

The Text Extractor Tool is a powerful tool designed to extract text from documents.
In other words, it converts documents into their text versions.
For example, it can convert PDF to text, image to text, etc.

## Required Environment Variables

| Variable                   | Description                                                                |
| -------------------------- | -------------------------------------------------------------------------- |
| `PLATFORM_SERVICE_HOST`    | The host where the platform service is running                             |
| `PLATFORM_SERVICE_PORT`    | The port where the service is listening                                    |
| `PLATFORM_SERVICE_API_KEY` | The API key for the platform                                               |
| `TOOL_DATA_DIR`            | The directory in the filesystem which contains contents for tool execution |
| `X2TEXT_HOST`              | The host where the x2text service is running                               |
| `X2TEXT_PORT`              | The port where the x2text service is listening                             |

## Setting Up a Dev Environment

1. Setup a virtual environment and activate it:

```commandline
python -m venv .venv
source .venv/bin/activate
```
2. Install the dependencies for the tool.

    Two Options
    - Install by Pypi version
        ```commandline
        pip install -r requirements.txt
        ```
    - To use the local development version of the [unstract-sdk](https://pypi.org/project/unstract-sdk/) install it from the local repository.
    Replace the path with the path to your local repository
        ```commandline
        pip install -e ~/path_to_repo/sdks/.
        ```

#### Tool execution preparation

1. Load the environment variables for the tool.
Make a copy of the `sample.env` file and name it `.env`. Fill in the required values.
They get loaded with [python-dotenv](https://pypi.org/project/python-dotenv/) through the SDK.

2. Update the tool's `data_dir` marked by the `TOOL_DATA_DIR` env. This has to be done before each tool execution since the tool updates the `INFILE` and `METADATA.json`.

#### Run SPEC command

Represents the JSON schema for the runtime configurable `settings` of a tool
```commandline
python main.py --command SPEC
```

#### Run PROPERTIES command

Describes some metadata for the tool such as its `version`, `description`, `inputs` and `outputs`
```commandline
python main.py --command PROPERTIES
```

#### Run ICON command

Returns the SVG icon for the tool, used by Unstract's frontend
```commandline
python main.py --command ICON
```

#### Run VARIABLES command

Represents the runtime variables or envs that will be used by the tool
```commandline
python main.py --command VARIABLES
```

#### Run RUN command


The schema of the JSON required for settings can be found by running the [SPEC](#run-spec-command) command. Alternatively if you have access to the code base, it is located in the `config` folder as `spec.json`.

```commandline
python main.py \
    --command RUN \
    --settings '{
        "extractorId": "<extractor_id of adapter>"
        }' \
    --workflow-id '00000000-0000-0000-0000-000000000000' \
    --log-level DEBUG

```
### Testing the tool from its docker image

Build the tool docker image from the folder containing the `Dockerfile` with
```commandline
docker build -t unstract/tool-example:0.0.1 .
```

Make sure the directory pointed by `TOOL_DATA_DIR` has the required information for the tool to run and 
necessary services like the `platform-service` is up.
To test the tool from its docker image, run the following command

```commandline
docker run -it \
    --network unstract-network \
    --env-file .env \
    -v "$(pwd)"/data_dir:/app/data_dir \
    unstract/tool-example:0.0.1 \
    --command RUN \
    --settings '{
        "extractorId": "<extractor_id of adapter>"
        }' \
    --workflow-id '00000000-0000-0000-0000-000000000000' \
    --log-level DEBUG

```
