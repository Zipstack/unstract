# Tool Registry

## Overview
The Tool Registry is a crucial component of our platform that enables the registration and management of various tools.
This document explains the structure of the Tool Registry and provides instructions on how to add new tools to it.


## Registry Configuration
The Tool Registry relies on the `registry.yaml` file to maintain a comprehensive list of registered tools. These tools may encompass private tools, distinct from the publicly available **tools** that are listed in `public-tools.json`. Private tools cater to specific use cases or are intended for privileged access.


## Registry
- Registry.yaml is used to register new private tools apart from the publicly available unstract tools

## Public Tools
- Public tools are openly accessible to all organizations and are readily available in the platform's hub. These public tools are cataloged in `public_tools.json`.

## Private Tools
- In contrast, private tools are documented in the `private_tools.json` file. These tools are designated for restricted or specialized use and are not accessible to the general public via the cloud platform

## Registering New Tools (Private Tools)
1. Build the docker image for the tool that needs to be registered. This can be done with the Dockerfile residing in the tool's folder.
Optionally this can be pushed to a registry of your choice.
```
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
1. Run the [load_tools_to_json.py](/unstract/tool-registry/scripts/load_tools_to_json.py) script. This script is responsible for processing the registry.yaml file and updating the private_tools.json file.
1. Once the script has executed, the Tool Registry will be updated with the newly registered private tools.
1. Users of the platform will be able to access and utilize all tools listed in both the private_tools.json and public_tools.json files. This ensures that all available tools are accessible to the platform's users, whether they are public or private.


By following these steps, you can effectively add new private tools to the Tool Registry and make them available within the platform, enhancing the capabilities and offerings of the system.
