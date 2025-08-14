import functools
import logging
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

import requests
from requests import ConnectionError, RequestException, Response
from unstract.sdk1.constants import MimeType, RequestHeader, ToolEnv
from unstract.sdk1.platform import PlatformHelper
from unstract.sdk1.tool.base import BaseTool
from unstract.sdk1.utils.common import log_elapsed

logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def handle_service_exceptions(context: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to handle exceptions in PromptTool service calls.

    Args:
        context (str): Context string describing where the error occurred
    Returns:
        Callable: Decorated function that handles service exceptions
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return func(*args, **kwargs)
            except ConnectionError as e:
                msg = f"Error while {context}. Unable to connect to prompt service."
                logger.error(f"{msg}\n{e}")
                args[0].tool.stream_error_and_exit(msg, e)
            except RequestException as e:
                error_message = str(e)
                response = getattr(e, "response", None)
                if response is not None:
                    if (
                        MimeType.JSON in response.headers.get("Content-Type", "").lower()
                        and "error" in response.json()
                    ):
                        error_message = response.json()["error"]
                    elif response.text:
                        error_message = response.text
                msg = f"Error while {context}. {error_message}"
                args[0].tool.stream_error_and_exit(msg, e)

        return wrapper

    return decorator


class PromptTool:
    """Class to handle prompt service methods for Unstract Tools."""

    def __init__(
        self,
        tool: BaseTool,
        prompt_host: str,
        prompt_port: str,
        is_public_call: bool = False,
        request_id: str | None = None,
    ) -> None:
        """Class to interact with prompt-service.

        Args:
            tool (AbstractTool): Instance of AbstractTool
            prompt_host (str): Host of platform service
            prompt_port (str): Port of platform service
            is_public_call (bool): Whether the call is public. Defaults to False
        """
        self.tool = tool
        self.base_url = PlatformHelper.get_platform_base_url(prompt_host, prompt_port)
        self.is_public_call = is_public_call
        self.request_id = request_id
        if not is_public_call:
            self.bearer_token = tool.get_env_or_die(ToolEnv.PLATFORM_API_KEY)

    @log_elapsed(operation="ANSWER_PROMPTS")
    @handle_service_exceptions("answering prompt(s)")
    def answer_prompt(
        self,
        payload: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url_path = "answer-prompt"
        if self.is_public_call:
            url_path = "answer-prompt-public"
        return self._call_service(
            url_path=url_path, payload=payload, params=params, headers=headers
        )

    @log_elapsed(operation="INDEX")
    @handle_service_exceptions("indexing")
    def index(
        self,
        payload: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        url_path = "index"
        if self.is_public_call:
            url_path = "index-public"
        prompt_service_response = self._call_service(
            url_path=url_path,
            payload=payload,
            params=params,
            headers=headers,
        )
        return prompt_service_response.get("doc_id")

    @log_elapsed(operation="EXTRACT")
    @handle_service_exceptions("extracting")
    def extract(
        self,
        payload: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url_path = "extract"
        if self.is_public_call:
            url_path = "extract-public"
        prompt_service_response = self._call_service(
            url_path=url_path,
            payload=payload,
            params=params,
            headers=headers,
        )
        return prompt_service_response.get("extracted_text")

    @log_elapsed(operation="SINGLE_PASS_EXTRACTION")
    @handle_service_exceptions("single pass extraction")
    def single_pass_extraction(
        self,
        payload: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._call_service(
            url_path="single-pass-extraction",
            payload=payload,
            params=params,
            headers=headers,
        )

    @log_elapsed(operation="SUMMARIZATION")
    @handle_service_exceptions("summarizing")
    def summarize(
        self,
        payload: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._call_service(
            url_path="summarize",
            payload=payload,
            params=params,
            headers=headers,
        )

    def _get_headers(self, headers: dict[str, str] | None = None) -> dict[str, str]:
        """Get default headers for requests.

        Returns:
            dict[str, str]: Default headers including request ID and authorization
        """
        request_headers = {RequestHeader.REQUEST_ID: self.request_id}
        if self.is_public_call:
            return request_headers
        request_headers.update(
            {RequestHeader.AUTHORIZATION: f"Bearer {self.bearer_token}"}
        )

        if headers:
            request_headers.update(headers)
        return request_headers

    def _call_service(
        self,
        url_path: str,
        payload: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        method: str = "POST",
    ) -> dict[str, Any]:
        """Communicates to prompt service to fetch response for the prompt.

        Only POST calls are made to prompt-service though functionality exists.

        Args:
            url_path (str): URL path to the service endpoint
            payload (dict, optional): Payload to send in the request body
            params (dict, optional): Query parameters to include in the request
            headers (dict, optional): Headers to include in the request
            method (str): HTTP method to use for the request (GET or POST)

        Returns:
            dict: Response from the prompt service
        """
        url: str = f"{self.base_url}/{url_path}"
        req_headers = self._get_headers(headers)
        response: Response = Response()
        if method.upper() == "POST":
            response = requests.post(
                url=url, json=payload, params=params, headers=req_headers
            )
        elif method.upper() == "GET":
            response = requests.get(url=url, params=params, headers=req_headers)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        response.raise_for_status()
        return response.json()
