import json
import logging
import os
from typing import Any, Optional, Union

import requests
from unstract.tool_sandbox.constants import UnstractWorker

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
        worker_host = os.environ.get("UNSTRACT_WORKER_HOST")
        worker_port = os.environ.get("UNSTRACT_WORKER_PORT")
        self.base_url = f"{worker_host}:{worker_port}{UnstractWorker.BASE_API_ENDPOINT}"
        self.organization_id = str(organization_id)
        self.workflow_id = str(workflow_id)
        self.execution_id = str(execution_id)
        self.envs = environment_variables
        self.messaging_channel = str(messaging_channel)

    def convert_str_to_dict(self, data: Union[str, dict[str, Any]]) -> dict[str, Any]:
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
    ) -> Optional[dict[str, Any]]:
        """Make unstract worker Get request.

        Args:
            image_name (str): _description_
            image_tag (str): _description_
            endpoint (str): _description_

        Returns:
            Optional[dict[str, Any]]: _description_
        """
        url = f"{self.base_url}{endpoint}"
        params = {"image_name": image_name, "image_tag": image_tag}
        response = requests.get(url, params=params, timeout=60)
        result: Optional[dict[str, Any]] = None
        if response.status_code == 200:
            result = response.json()
        elif response.status_code == 404:
            logger.error(
                f"Error while calling tool {image_name}: "
                f"for tool instance status code {response.status_code}"
            )
        else:
            logger.error(
                f"Error while calling tool {image_name} " f" reason: {response.reason}"
            )
        return result

    def call_tool_handler(
        self,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Calling unstract worker to run the required tool.

        Args:
            image_name (str): image name
            image_tag (str): image tag
            params (dict[str, Any]): tool params
            settings (dict[str, Any]): tool settings

        Returns:
            Optional[dict[str, Any]]: tool response
        """
        url = f"{self.base_url}{UnstractWorker.RUN_API_ENDPOINT}"
        data = self.create_tool_request_data(
            image_name,
            image_tag,
            settings,
        )

        response = requests.post(url, json=data, timeout=60)
        result: Optional[dict[str, Any]] = None
        if response.status_code == 200:
            result = response.json()
        elif response.status_code == 404:
            logger.error(
                f"Error while calling tool {image_name}: "
                f"for tool instance status code {response.status_code}"
            )
        else:
            logger.error(
                f"Error while calling tool {image_name} " f" reason: {response.reason}"
            )
        return result

    def create_tool_request_data(
        self,
        image_name: str,
        image_tag: str,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        data = {
            "image_name": image_name,
            "image_tag": image_tag,
            "organization_id": self.organization_id,
            "workflow_id": self.workflow_id,
            "execution_id": self.execution_id,
            "settings": settings,
            "envs": self.envs,
            "messaging_channel": self.messaging_channel,
        }
        return data
