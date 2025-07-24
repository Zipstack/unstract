import json
import logging
from typing import Any

import requests
from requests import ConnectionError, RequestException, Response
from requests.exceptions import ConnectionError, HTTPError

from unstract.sdk1.constants import (
    AdapterKeys,
    LogLevel,
    MimeType,
    PromptStudioKeys,
    PublicAdapterKeys,
    RequestHeader,
    ToolEnv,
)
from unstract.sdk1.exceptions import SdkError
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils.common import Utils

logger = logging.getLogger(__name__)


class PlatformHelper:
    """Helper to interact with platform service.

    Notes:
        - PLATFORM_SERVICE_API_KEY environment variable is required.
    """
    def __init__(
        self,
        tool: BaseTool,
        platform_host: str,
        platform_port: str,
        request_id: str | None = None,
    ) -> None:
        """Constructor for helper to connect to platform service.

        Args:
            tool (AbstractTool): Instance of AbstractTool
            platform_host (str): Host of platform service
            platform_port (str): Port of platform service
            request_id (str | None, optional): Request ID for the service.
                Defaults to None.
        """
        self.tool = tool
        self.base_url = PlatformHelper.get_platform_base_url(platform_host, platform_port)
        self.bearer_token = tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)
        self.request_id = request_id

    @classmethod
    def get_platform_base_url(cls, platform_host: str, platform_port: str) -> str:
        """Make base url from host and port.

        Args:
            platform_host (str): Host of platform service
            platform_port (str): Port of platform service

        Returns:
            str: URL to the platform service
        """
        if platform_host[-1] == "/":
            return f"{platform_host[:-1]}:{platform_port}"
        return f"{platform_host}:{platform_port}"

    @classmethod
    def is_public_adapter(cls, adapter_id: str) -> bool:
        """Check if the given adapter_id is one of the public adapter keys.

        This method iterates over the attributes of the PublicAdapterKeys class
        and checks if the provided adapter_id matches any of the attribute values.

        Args:
            adapter_id (str): The ID of the adapter to check.

        Returns:
            bool: True if the adapter_id matches any public adapter key,
            False otherwise.
        """
        try:
            for attr in dir(PublicAdapterKeys):
                if getattr(PublicAdapterKeys, attr) == adapter_id:
                    return True
            return False
        except Exception as e:
            logger.warning(
                f"Unable to determine if adapter_id: {adapter_id}"
                f"is public or not: {str(e)}"
            )
            return False

    @classmethod
    def _get_adapter_configuration(
        cls, adapter_instance_id: str,
    ) -> dict[str, Any]:
        """Get Adapter
            1. Get the adapter config from platform service
            using the adapter_instance_id

        Args:
            adapter_instance_id (str): Adapter instance ID

        Returns:
            dict[str, Any]: Config stored for the adapter
        """
        url = f"{self.base_url}/adapter_instance"
        query_params = {AdapterKeys.ADAPTER_INSTANCE_ID: adapter_instance_id}
        headers = {"Authorization": f"Bearer {self.bearer_token}"}
        try:
            response = requests.get(url, headers=headers, params=query_params)
            response.raise_for_status()
            adapter_data: dict[str, Any] = response.json()

            # Removing name and type to avoid migration for already indexed records
            adapter_name = adapter_data.pop("adapter_name", "")
            adapter_type = adapter_data.pop("adapter_type", "")
            provider = adapter_data.get("adapter_id", "").split("|")[0]
            # TODO: Print metadata after redacting sensitive information
            self.tool.stream_log(
                f"Retrieved config for '{adapter_instance_id}', type: "
                f"'{adapter_type}', provider: '{provider}', name: '{adapter_name}'",
                level=LogLevel.DEBUG,
            )
        except ConnectionError:
            raise SdkError(
                "Unable to connect to platform service, please contact the admin."
            )
        except HTTPError as e:
            default_err = (
                "Error while calling the platform service, please contact the admin."
            )
            msg = Utils.get_msg_from_request_exc(
                err=e, message_key="error", default_err=default_err
            )
            raise SdkError(f"Error retrieving adapter. {msg}")
        return adapter_data

    @classmethod
    def get_adapter_config(
        cls, tool: BaseTool, adapter_instance_id: str
    ) -> dict[str, Any] | None:
        """Get adapter spec by the help of unstract DB tool.

        This method first checks if the adapter_instance_id matches
        any of the public adapter keys. If it matches, the configuration
        is fetched from environment variables. Otherwise, it connects to the
        platform service to retrieve the configuration.

        Args:
            tool (AbstractTool): Instance of AbstractTool
            adapter_instance_id (str): ID of the adapter instance
        Required env variables:
            PLATFORM_HOST: Host of platform service
            PLATFORM_PORT: Port of platform service
        Returns:
            dict[str, Any]: Config stored for the adapter
        """
        # Check if the adapter ID matches any public adapter keys
        if PlatformHelper.is_public_adapter(adapter_id=adapter_instance_id):
            adapter_metadata_config = tool.get_env_or_die(adapter_instance_id)
            adapter_metadata = json.loads(adapter_metadata_config)
            return adapter_metadata
        platform_host = tool.get_env_or_die(ToolEnv.PLATFORM_HOST)
        platform_port = tool.get_env_or_die(ToolEnv.PLATFORM_PORT)

        tool.stream_log(
            f"Retrieving config from DB for '{adapter_instance_id}'",
            level=LogLevel.DEBUG,
        )
        return self._get_adapter_configuration(adapter_instance_id)

    def _get_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Get default headers for requests.

        Returns:
            dict[str, str]: Default headers including request ID and authorization
        """
        request_headers = {
            RequestHeader.REQUEST_ID: self.request_id,
            RequestHeader.AUTHORIZATION: f"Bearer {self.bearer_token}",
        }
        if headers:
            request_headers.update(headers)
        return request_headers

    def _call_service(
        self,
        url_path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Talks to platform-service to make GET / POST calls.

        Only GET calls are made to platform-service though functionality exists.

        Args:
            url_path (str): URL path to the service endpoint
            payload (dict, optional): Payload to send in the request body
            params (dict, optional): Query parameters to include in the request
            headers (dict, optional): Headers to include in the request
            method (str): HTTP method to use for the request (GET or POST)

        Returns:
            dict: Response from the platform service

            Sample Response:
            {
                "status": "OK",
                "error": "",
                structure_output : {}
            }
        """
        url: str = f"{self.base_url}/{url_path}"
        req_headers = self._get_headers(headers)
        response: Response = Response()
        try:
            if method.upper() == "POST":
                response = requests.post(
                    url=url, json=payload, params=params, headers=req_headers
                )
            elif method.upper() == "GET":
                response = requests.get(url=url, params=params, headers=req_headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
        except ConnectionError as connect_err:
            msg = "Unable to connect to platform service. Please contact admin."
            msg += " \n" + str(connect_err)
            self.tool.stream_error_and_exit(msg)
        except RequestException as e:
            # Extract error information from the response if available
            error_message = str(e)
            content_type = response.headers.get("Content-Type", "").lower()
            if MimeType.JSON in content_type:
                response_json = response.json()
                if "error" in response_json:
                    error_message = response_json["error"]
            elif response.text:
                error_message = response.text
            self.tool.stream_error_and_exit(
                f"Error from platform service. {error_message}"
            )
        return response.json()

    def get_platform_details(self) -> dict[str, Any] | None:
        """Obtains platform details associated with the platform key.

        Currently helps fetch organization ID related to the key.

        Returns:
            Optional[dict[str, Any]]: Dictionary containing the platform details
        """
        response = self._call_service(
            url_path="platform_details",
            payload=None,
            params=None,
            headers=None,
            method="GET",
        )
        return response.get("details")

    def get_prompt_studio_tool(self, prompt_registry_id: str) -> dict[str, Any]:
        """Get exported custom tool by the help of unstract DB tool.

        Args:
            prompt_registry_id (str): ID of the prompt_registry_id
        Required env variables:
            PLATFORM_HOST: Host of platform service
            PLATFORM_PORT: Port of platform service
        """
        query_params = {PromptStudioKeys.PROMPT_REGISTRY_ID: prompt_registry_id}
        return self._call_service(
            url_path="custom_tool_instance",
            payload=None,
            params=query_params,
            headers=None,
            method="GET",
        )

    def get_llm_profile(self, llm_profile_id: str) -> dict[str, Any]:
        """Get llm profile by the help of unstract DB tool.

        Args:
            llm_profile_id (str): ID of the llm_profile_id
        Required env variables:
            PLATFORM_HOST: Host of platform service
            PLATFORM_PORT: Port of platform service
        """
        query_params = {PromptStudioKeys.LLM_PROFILE_ID: llm_profile_id}
        return self._call_service(
            url_path="llm_profile_instance",
            payload=None,
            params=query_params,
            headers=None,
            method="GET",
        )
        