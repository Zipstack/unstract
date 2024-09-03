# Tool Registry

## Overview

The Tool Registry is a crucial component of our platform that enables the registration and management of various tools.
This document explains the structure of the Tool Registry and provides instructions on how to add new tools to it.

## Registry Configuration

The Tool Registry relies on a `registry.yaml` file to maintain a comprehensive list of registered tools. Tools can be made public or private. In order for the tool registry configuration to be used, set the env `TOOL_REGISTRY_CONFIG_PATH` wherever this library is imported and used.

### Registry

- `registry.yaml` helps register tools by specifying a tool image and version from a container registry.

### Public Tools

- Public tools are openly accessible to all organizations and are readily available in the platform's `Workflows` page. These public tools are cataloged in `public_tools.json`. They are pulled from Docker hub and hence require no authentication.

### Private Tools

- In contrast, private tools are documented in the `private_tools.json` file. This file is not tracked by git. These tools are meant for restricted or specialized use and are visible only to the running Unstract instance. They are generally pulled from a supported private container registry and hence require authentication.

## Registering New Tools (Private Tools)

1. Build the docker image for the tool that needs to be registered. This can be done with the Dockerfile residing in the [tool's folder](/tools/).
Optionally this can be pushed to a registry of your choice.

    ```bash
    docker build --pull --rm -f "tools/<tool_folder>/Dockerfile" -t <image_name>:<image_tag>
    ```

1. Refer the [sample_registry.yaml](/unstract/tool-registry/src/unstract/tool_registry/config/sample_registry.yaml) and create a new `registry.yaml` with your desired tools.
1. You can specify the tool's location using one of the following methods:
    - Local Path: If the tool is stored locally on your system, you can define it like this. The default tag is `latest`

        ```yml
        tools:
           - local:<tool_image_name>:<tool_image_tag>
        ```

    - Docker: If the tool is available as a Docker image, define it as follows. The default tag is `latest`

        ```yml
        tools:
           - docker:unstract/<tool_image_name>:<tool_image_tag>
        ```

1. Run the [load_tools_to_json.py](/unstract/tool-registry/scripts/load_tools_to_json.py) script. This script uses the `registry.yaml file` and updates the `private_tools.json` file.
1. Once the script has executed, the **Tool Registry** will be updated with the newly registered private tools.
1. Optionally in order to make the tool public, move the generated JSON to `public_tools.json` and commit the changes.
1. Users of the platform will be able to access and utilize all tools listed in both the user's `private_tools.json` and `public_tools.json` files. This ensures that all available tools are accessible to the platform's users, whether they are public or private.

By following these steps, you can effectively add new private tools to the Tool Registry and make them available within the platform, enhancing the capabilities and offerings of the system.
