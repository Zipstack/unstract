import json
import logging
import os
from typing import Any

import requests

from unstract.core.utilities import UnstractUtils
from unstract.tool_sandbox.constants import UnstractRunner

logger = logging.getLogger(__name__)


class ToolSandboxHelper:
    def __init__(
        self,
        organization_id: str,
        workflow_id: str,
        execution_id: str,
        messaging_channel: str,
        environment_variables: dict[str, str],
    ) -> None:
        runner_host = os.environ.get("UNSTRACT_RUNNER_HOST")
        runner_port = os.environ.get("UNSTRACT_RUNNER_PORT")
        self.base_url = f"{runner_host}:{runner_port}{UnstractRunner.BASE_API_ENDPOINT}"
        self.organization_id = str(organization_id)
        self.workflow_id = str(workflow_id)
        self.execution_id = str(execution_id)
        self.envs = environment_variables
        self.messaging_channel = str(messaging_channel)

    def convert_str_to_dict(self, data: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(data, str):
            output: dict[str, Any] = {}
            try:
                output = json.loads(data)
            except json.JSONDecodeError as e:
                logger.error(f"Error decoding JSON: {e}")
            return output
        return data

    def make_get_request(
        self, image_name: str, image_tag: str, endpoint: str
    ) -> dict[str, Any] | None:
        """Make unstract runner Get request.

        Args:
            image_name (str): _description_
            image_tag (str): _description_
            endpoint (str): _description_

        Returns:
            Optional[dict[str, Any]]: _description_
        """
        url = f"{self.base_url}{endpoint}"
        params = {"image_name": image_name, "image_tag": image_tag}
        response = requests.get(url, params=params)
        result: dict[str, Any] | None = None
        if response.status_code == 200:
            result = response.json()
        elif response.status_code == 404:
            logger.error(
                f"Error while calling tool {image_name}: "
                f"for tool instance status code {response.status_code}"
            )
        else:
            logger.error(
                f"Error while calling tool {image_name} reason: {response.reason}"
            )
        return result

    def call_tool_handler(
        self,
        file_execution_id: str,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
        retry_count: int | None = None,
    ) -> dict[str, Any] | None:
        """Calling unstract runner to run the required tool.

        Args:
            image_name (str): image name
            image_tag (str): image tag
            params (dict[str, Any]): tool params
            settings (dict[str, Any]): tool settings

        Returns:
            Optional[dict[str, Any]]: tool response
        """
        url = f"{self.base_url}{UnstractRunner.RUN_API_ENDPOINT}"
        headers = {
            "X-Request-ID": file_execution_id,
        }
        data = self.create_tool_request_data(
            file_execution_id, image_name, image_tag, settings, retry_count
        )

        response = requests.post(url, headers=headers, json=data)
        result: dict[str, Any] | None = None
        if response.status_code == 200:
            result = response.json()
        elif response.status_code == 404:
            logger.error(
                f"Error while calling tool {image_name}: "
                f"for tool instance status code {response.status_code}"
            )
        else:
            logger.error(
                f"Error while calling tool {image_name} reason: {response.reason}"
            )
        return result

    def create_tool_request_data(
        self,
        file_execution_id: str,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
        retry_count: int | None = None,
    ) -> dict[str, Any]:
        container_name = UnstractUtils.build_tool_container_name(
            tool_image=image_name,
            tool_version=image_tag,
            file_execution_id=file_execution_id,
            retry_count=retry_count,
        )
        data = {
            "image_name": image_name,
            "image_tag": image_tag,
            "organization_id": self.organization_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "file_execution_id": file_execution_id,
            "container_name": container_name,
            "settings": settings,
            "envs": self.envs,
            "messaging_channel": self.messaging_channel,
        }
        return data
