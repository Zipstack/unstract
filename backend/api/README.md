# API Deployment Documentation

## Possible HTTP Status Codes

- **200 OK**: The request was successful.
- **400 Bad Request**: The request could not be understood or was missing required parameters.
- **401 Unauthorized**: Authentication failed or user does not have permission for the requested operation.
- **403 Forbidden**: The API key is missing or invalid.
- **404 Not Found**: The requested resource could not be found (Or Incorrect API URl).a
- **422 Unprocessable Entity**: Validation error, the input could not be processed.
- **500 Internal Server Error**: An error occurred on the server.

## API Structure

### URL Structure

> <base_domain_url>/deployment/api/<organization_id>/<api_name>/


- `<base_domain_url>`: The base URL where the API is hosted (e.g., https://api.example.com).
- `<organization_id>`: Unique identifier for the organization making the request.
- `<api_name>`: Name of the API or workflow being executed.

Example:

`https://example.unstract.com/deployment/api/organization123/myapi/`

### Headers
- **Authorization Header**: `Bearer <api_key>`
Ensure that the API key provided in the header is valid and has permissions for the requested operation.

#### Example:

```http
Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234567890
```

### Body Structure
- `files`: Path to the file(s) (**Required**) (File)
  - Specifies the file(s) to be processed. Multiple files can be provided, but the result will be completed only after all files have been processed.
- `timeout`: The maximum time (in seconds) to wait for execution before timing out (**Optional**)
  - Specifies how long to wait for the API to complete the operation before timing out. The value can range from 0 to 300 seconds. If omitted, the request will execute in the background without a timeout.
---

## API Responses

The API provides several types of responses depending on the request status and the execution result.

### Standard Respons
This response is returned when a request is processed, and execution is initiated.

```json
{
    "message": {
        "execution_status": "<Current_status>",  // Current Status of execution
        "status_api": "<Status API with execution ID>",
        "error": null,
        "result": null
    }
}
```

- `execution_status`: The current status of the workflow execution (e.g., "PENDING", "EXECUTING", "COMPLETED").
- `status_api`: The URL that can be used to check the status of the execution.
- `error`: Any error details if applicable.
- `result`: The results of the execution, if available.

### Timeout Scenario
If the execution is not completed within the specified timeout period, the client can check the result later using the status_api.

Example response when the timeout occurs:

```json
{
    "message": {
        "execution_status": "<Current Status>",
        "status_api": "/deployment/api/<organization_id>/<api_name>/?execution_id=<execution_id>",
        "error": null,
        "result": null
    }
}
```
- `status_api`: URL to check the status of the execution after the timeout.
- `execution_status`: Shows the current status of the execution (e.g., "EXECUTING", "PENDING").

### Completed Execution with Results

When the execution completes, a response with detailed results is provided.


```json
{
    "message": {
        "execution_status": "COMPLETED",
        "status_api": "/deployment/api/<organization_id>/<api_name>/?execution_id=<execution_id>",
        "error": null,
        "result": [
            {
                "file": "<file_name>",
                "status": "Success",
                "result": {
                    "input_file": "<input_file_name>",
                    "result": "<execution result of the file>"
                },
                "metadata": {
                    "source_name": "<source file name>",
                    "source_hash": "<hash value of the file>",
                    "organization_id": "<organization_id>",
                    "workflow_id": "<workflow_id>",
                    "total_elapsed_time": "<total_time>",
                    "tool_metadata": [<list_of_tools_used_during_execution>]
                }
            }
        ]
    }
}
```

- `file`: The name of the file processed.
- `status`: Success or failure status of the execution.
- `result`: The outcome of the execution for each file, including the result and metadata related to the file and workflow.
- `metadata`: Additional details such as source file name, file hash, workflow ID, and total time taken.

### Execution Error

If an error occurs during the execution process, the response will provide details about each file that failed. This helps in understanding what went wrong and allows for corrective actions


```json
{
    "message": {
        "execution_status": "ERROR",
        "status_api": "/deployment/api/<organization_id>/<api_name>/?execution_id=<execution_id>",
        "error": null,
        "result": [
            {
                "file": "<file_name>",
                "status": "Failed",
                "error": "<Error details or hint>"
            }
        ]
    }
}
```

- `file`: The name of the file that failed.
- `status`: The processing status of the file, which is "Failed".
- `error`: Detailed error message or a hint about what went wrong.

#### Next Steps:

- **Check Logs:** To get more detailed information about the error, refer to the logs for the API using the provided execution_id.
- **Contact Admin:** If the logs do not provide sufficient information or if further assistance is needed, contact the administrator for additional details.

### Mixed Results

If the execution process results in a mix of successful and failed files, the response will include detailed results for each file. This allows you to see which files were processed successfully and which encountered issues.

```json
{
    "message": {
        "execution_status": "COMPLETED",
        "status_api": "/deployment/api/<organization_id>/<api_name>/?execution_id=<execution_id>",
        "error": null,
        "result": [
            {
                "file": "<file_name>",
                "status": "Failed",
                "error": "<Error details or hint>"
            },
            {
                "file": "<file_name>",
                "status": "Success",
                "result": {
                    "input_file": "<input_file_name>",
                    "result": "<execution result of the file>"
                },
                "metadata": {
                    "source_name": "<source file name>",
                    "source_hash": "<hash value>",
                    "organization_id": "<organization_id>",
                    "workflow_id": "<workflow_id>",
                    "total_elapsed_time": "<total_time>",
                    "tool_metadata": [<list_of_tools_used>]
                }
            }
        ]
    }
}
```

## Different Response Codes

Below are some common response codes and their meanings:

### 422: Client Error Example

This response indicates that the pipeline is inactive, and the execution cannot proceed.


```json
{
    "type": "client_error",
    "errors": [
        {
            "code": "error",
            "detail": "Pipeline 'testetl' is inactive, please activate the pipeline",
            "attr": null
        }
    ]
}
```

### 400: Missing File

This response occurs when the files parameter is missing or empty.


```json
{
    "type": "client_error",
    "errors": [
        {
            "code": "error",
            "detail": "File shouldn't be empty",
            "attr": null
        }
    ]
}
```

### 200: Executing in Background

This response is returned when the execution is still ongoing, and the results are not yet available.


```json
{
    "message": {
        "execution_status": "EXECUTING",
        "status_api": "/deployment/api/<organization_id>/<api_name>/?execution_id=<execution_id>",
        "error": null,
        "result": null
    }
}
```

### 200: Completed

This response is returned when execution is completed, and the results are available.


```json
{
    "status": "COMPLETED",
    "message": []  // Results
}
```

### 200: Pending

This response indicates that the execution is queued but has not started.


```json
{
    "message": {
        "execution_status": "PENDING",
        "status_api": "/deployment/api/<organization_id>/<api_name>/?execution_id=<execution_id>",
        "error": null,
        "result": null
    }
}
```

### 400: Validation Error

A validation error occurs when an invalid parameter is passed, such as a non-integer value for timeout.


```json
{
    "type": "validation_error",
    "errors": [
        {
            "code": "invalid",
            "detail": "A valid integer is required.",
            "attr": "timeout"
        }
    ]
}
```

### 403: Forbidden

The API key is missing or invalid, preventing the request from proceeding.


```json
{
    "type": "client_error",
    "errors": [
        {
            "code": "error",
            "detail": "Missing API key",
            "attr": null
        }
    ]
}
```

### 500: Server Error

A 500 Internal Server Error indicates that something went wrong on the server during the processing of the request. This is a general error when the server encounters an unexpected condition that prevents it from fulfilling the request.


### 401: Unauthorized

A 401 Unauthorized error is returned when the request lacks proper authentication credentials, such as a missing or invalid API key. This means that the user is not authorized to access the requested resource.
```json
{
    "type": "client_error",
    "errors": [
        {
            "code": "error",
            "detail": "Unauthorized",
            "attr": null
        }
    ]
}
```

### 404: Not Found

This response occurs when the API name or URL is invalid, meaning the requested resource could not be found on the server. This can happen if the API name in the URL is incorrect or does not exist. Ensure that the `organization_id` and `api_name` are correctly specified in the request URL.

invalid api name (invalid api url)
```json
{
    "type": "client_error",
    "errors": [
        {
            "code": "error",
            "detail": "API not found",
            "attr": null
        }
    ]
}
```
#### Possible Causes:

- The `api_name` is misspelled or does not match an existing API.
- The `organization_id` is incorrect or does not exist in the system.
- The API endpoint is not available or has been removed.

Check the list of available APIs for the organization to confirm the correct name.
