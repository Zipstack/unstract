### Introduction

Tools for Unstract can be written in any language. The only requirement is that they need to be containerised and expose
a script which follows the Unstract tools protocol.

### Unstract tools protocol

All input and output for the tool is done through the standard input and output streams. The tool is expected to read
the input from the standard input stream and write the output to the standard output stream. The input is a JSON object
and the output is newline seperated JSON objects. The input for most commands will be in the form of command line
arguments. Input JSONs from standard input might not be required.

#### Tool definition

```json
{
  "display_name": "Document Indexer",
  "function_name": "document_indexer",
  "description": "This tool creates indexes and embeddings for documents.",
  "parameters": [
    {
      "name": "input_file",
      "type": "string",
      "description": "File path of the input file"
    }
  ],
  "versions": [
    "1.0.0"
  ],
  "is_cacheable": false,
  "input_type": "file",
  "output_type": "index",
  "requires": {
    "files": {
      "input": true,
      "output": false
    },
    "databases": {
      "input": false,
      "output": false
    }
  }
}
```

Tools are defined using the `config/properties.json` file. This json file contains standard properties for the tool,
explained below

`display_name`
: The name of the tool as displayed in the platform

`function_name`
: A unique name for the tool. This name is used to identify the tool in the platform. This name should be a valid
python function name. This name is also used to name the docker image for the tool. The docker image name is
`unstract/<function_name>`

`description`
: A short description of the tool. This description is displayed in the platform

`parameters`
: An *array* of json objects. Each json object represents a parameter for the tool. Each parameter object has the
following properties `name`, `type` and `description`. These are the _inputs_ to the tool.

`parameters[x].name`
: Is the name of the parameter. This name is used to identify the parameter in the platform.

`parameters[x].type`
: Is the type of the parameter. This type is used to validate the user input in the platform. The type can be `string`
or `number`.

`parameters[x].description`
: Is a short description of the parameter. This description is displayed in the platform.

`is_cachable`
: A boolean value indicating whether the tool is cachable or not. If the tool is cachable, the platform will allow
caching if the tool is setup to cache.

`input_type`
: The type of input for the tool. This can be `file`, `db` or `index`

`output_type`
: The type of output for the tool. This can be `file`, `db` or `index`

`required.files.input`
: A boolean value to indicate whether the tool requires input files or not.

`required.files.output`
: A boolean value to indicate whether the tool produces output files or not.

`required.db.input`
: A boolean value to indicate whether the tool requires input database or not.

`required.db.output`
: A boolean value to indicate whether the tool produces output database or not.

#### Tool settings

```json
{
  "title": "Document Indexer",
  "description": "Index documents based on their semantic content",
  "type": "object",
  "required": [
    "embeddingTransformer",
    "vectorStore"
  ],
  "properties": {
    "embeddingTransformer": {
      "type": "string",
      "title": "Embeddings",
      "description": "Embeddings to use",
      "enum": [
        "Azure OpenAI"
      ],
      "default": "Azure OpenAI"
    },
    "vectorStore": {
      "type": "string",
      "title": "Vector store",
      "description": "Vector store to use",
      "enum": [
        "Postgres pg_vector"
      ],
      "default": "Postgres pg_vector"
    },
    "overwrite": {
      "type": "boolean",
      "title": "Overwrite existing vectors",
      "default": false,
      "description": "Overwrite existing vectors"
    },
    "useCache": {
      "type": "boolean",
      "title": "Cache and use cached results",
      "default": true,
      "description": "Use cached results"
    }
  }
}
```

Tool settings are defined by default in `config/spec.json` file. This json schema is used to display the user input form in
the platform. The tool should collect all the information required for its working here. For example, if the tool
requires a username and password to connect to a database, the tool should collect these details in the settings form.
The settings form is displayed to the user when the tool is added to the workflow. You might also collect API keys and
other sensitive information here. The platform will provide this information to the tool through command line arguments
to the main tool script when it is called as part of the workflow or during debugging runs.

The json schema should be a valid json schema. You can use [jsonschema.net](https://jsonschema.net/) to generate a json
schema from a sample json. The json schema should be saved in `config/spec.json` file. The platform's front end
takes care of validating the user input against this schema. The platform's backend will pass the user input to the tool
as command line arguments.

#### Tool icon

The tool icon is defined in `config/icon.svg` file. This svg file is displayed in the platform. The icon should be a
square aspect ratio.


#### Tool runtime variables
```json
{
  "title": "Runtime Variables",
  "description": "Runtime Variables for translate",
  "type": "object",
  "required": [
    "GOOGLE_SERVICE_ACCOUNT"
  ],
  "properties": {
    "GOOGLE_SERVICE_ACCOUNT": {
      "type": "string",
      "title": "Google Service Account",
      "description": "Google Service account"
    }
  }
}
```

Tool runtime variables are defined in `config/runtime_variables.json` file. The JSON schema presented here defines the runtime variables required for the tool's operation. These variables are essential for the tool to function correctly. For instance, if the tool relies on an API key to connect to a third-party service, it must gather these details from the runtime variables form.

This form is displayed to users on the tool registration page in the frontend, ensuring that all necessary environment variables are provided for the tool's proper functioning.


#### Input and output protocol

> The preferred way to create the output jsons is to use the tools available in the `unstract` SDK. The SDK provides
> utility functions to create the output jsons. Please refer to the SDK documentation.

The protocol is based on simple text messages encapsulated in JSON.

List of message types:

- `SPEC`
- `PROPERTIES`
- `ICON`
- `VARIABLES`
- `LOG`
- `COST`
- `RESULT`
- `SINGLE_STEP_MESSAGE`

Message type details:

#### `SPEC` message

```json
{
  "type": "SPEC",
  "spec": "<SPEC JSON>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
}
``` 

The `spec` property contains the json from `spec.json`. Refer to [tool settings section](#tool-settings) for more details.

#### `PROPERTIES` message

```json
{
  "type": "PROPERTIES",
  "properties": "<PROPERTIES JSON>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
} 
```

The `properties` property contains the json from `properties.json`. Refer to [tool definition](#tool-definition) section for more

#### `ICON` message

```json
{
  "type": "ICON",
  "icon": "<ICON SVG>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
} 
```

The `icon` property contains the svg from `icon.svg`. Refer to *tool icon* section for more details. Note that this is
returns the SVG text itself and not the path to the SVG file.

#### `VARIABLES` message

```json
{
  "type": "VARIABLES",
  "variables": "<VARIABLES JSON>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
}
``` 

The `variables` property contains the json from `runtime_variables.json`. Refer to [Tool runtime variables section](#tool-runtime-variables) for more details.

#### `LOG` message

```json
{
  "type": "LOG",
  "level": "<LOG LEVEL>",
  "log": "<LOG MESSAGE>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
} 
```

The `log` property contains a log message. The level property can contain one
of `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`

#### `COST` message

```json
{
  "type": "COST",
  "cost": "<COST>",
  "cost_units": "<COST UNITS>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
} 
```

The `cost` property contains the cost of the tool run. The `cost` is a floating point number and `cost_units` is a
string

#### `RESULT` message

```json
{
  "type": "RESULT",
  "result": {
    "workflow_id": "<WORKFLOW_ID>",
    "elapsed_time": "<ELAPSED TIME>",
    "output": "<OUTPUT JSON or STRING>"
  },
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
} 
```

The `result` property contains the result of the tool run. The `result` is a json object. The `result` json object has a
standard format mentioned above.

#### `SINGLE_STEP_MESSAGE` message

```json
{
  "type": "SINGLE_STEP_MESSAGE",
  "message": "<MESSAGE>",
  "emitted_at": "<TIMESTAMP IN ISO FORMAT>"
} 
```

The `message` property contains a message to be displayed to the user. This message is displayed in the platform during
single stepping (debug mode). TODO: Add more details about single stepping and format of message
