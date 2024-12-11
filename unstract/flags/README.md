# FEATURE FLAGS

## Prerequisites

To effectively use this repository, it's beneficial to have a foundational understanding of basic gRPC functionality and experience working with gRPC in Python. Familiarity with concepts such as gRPC services, protocol buffers, and the structure of gRPC-based applications will enhance your ability to leverage the tools and code provided here.

Feature flags are a software development technique that allows you to enable or disable certain features in your application without deploying new code. Flipt is a feature flagging service that provides a centralized way to manage and control feature flags.

The following code demonstrates the usage of feature flags with the Flipt service running as a Docker container.

```python
def is_feature_enabled(feature_flag: str) -> bool:
    """
    Check if a feature flag is enabled.

    Args:
        feature_flag (str): The name of the feature flag to check.

    Returns:
        bool: True if the feature flag is enabled, False otherwise.
    """
    # Implementation code here
    pass

# Usage example
if is_feature_enabled("my_feature"):
    # Execute code for enabled feature
    pass
else:
    # Execute code for disabled feature
    pass
```

In this code, we are using Flipt to check the status of a feature flag before executing a specific block of code. The Flipt service is assumed to be running as a Docker container.

To use this code, make sure you have the Flipt service running as a Docker container and configure the necessary connection details in the code. Then, you can use the `is_feature_enabled` function to check the status of a feature flag before executing the corresponding code.

Note: This code assumes that you have already set up the necessary feature flags and configurations in the Flipt service.

For more information on feature flags and Flipt, refer to the documentation:

- Feature flags: https://en.wikipedia.org/wiki/Feature_toggle
- Flipt: https://flipt.io/

## Feature flags in Unstract

- Refer related files in `/backend/feature_flag` and `/unstract/flags`

- Set required variables in backend `.env` to utilize feature flags:

    ```bash
    EVALUATION_SERVER_IP=
    EVALUATION_SERVER_PORT=
    EVALUATION_SERVER_WARNINGS="true|false"
    ```

- Generate python files for gRPC using `.proto` file inside `feature_flags` app with `protoc`.
  The generated files have prefix `_pb`, indicating protocol buffers code.

    ```bash
    python -m grpc_tools.protoc -I protos --python_out=. --grpc_python_out=. protos/evaluation.proto

    protoc --python_out=./protos protos/evaluation.proto
    ```

## Explanation

The first command (`python -m grpc_tools.protoc ...`) generates the gRPC Python files (`_pb2.py` and `_pb2_grpc.py`) based on the `evaluation.proto` file located in the `protos` directory.

The second command (`protoc --python_out=./protos ...`) generates the standard Python files (`_pb2.py`) based on the same `evaluation.proto` file.

After running the compilation commands, you can use the generated files in your Python project to implement gRPC client and server functionality. Refer to the generated files for the specific classes and methods available for use.
