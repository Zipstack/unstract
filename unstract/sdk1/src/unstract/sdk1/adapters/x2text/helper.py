import logging
from typing import Any

import requests
from requests import Response
from requests.exceptions import ConnectionError, HTTPError, Timeout
from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.utils import AdapterUtils
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.constants import MimeType
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

logger = logging.getLogger(__name__)


class X2TextHelper:
    """Helpers meant for x2text adapters."""

    @staticmethod
    def parse_response(
        response: Response,
        out_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> tuple[str, bool]:
        """Parses the response from a request.

        Optionally it can write the output to a file

        Args:
            response (Response): Response to parse
            out_file_path (Optional[str], optional): Output file path to write
                 to, skipped if None or emtpy. Defaults to None.
            fs (FileStorage): file storage object to perfrom file operations

        Returns:
            tuple[str, bool]: Response's content and status of parsing
        """
        if not response.ok and not response.content:
            return "", False
        if isinstance(response.content, bytes):
            output = response.content.decode("utf-8")
        if out_file_path:
            fs.write(path=out_file_path, mode="w", encoding="utf-8", data=output)
        return output, True


class UnstructuredHelper:
    """Helpers meant for unstructured-community and unstructured-enterprise."""

    URL = "url"
    API_KEY = "api_key"
    TEST_CONNECTION = "test-connection"
    PROCESS = "process"

    @staticmethod
    def test_server_connection(unstructured_adapter_config: dict[str, Any]) -> bool:
        UnstructuredHelper.make_request(
            unstructured_adapter_config, UnstructuredHelper.TEST_CONNECTION
        )
        return True

    @staticmethod
    def process_document(
        unstructured_adapter_config: dict[str, Any],
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage = FileStorage(provider=FileStorageProvider.LOCAL),
    ) -> str:
        try:
            response: Response
            local_storage = FileStorage(FileStorageProvider.LOCAL)
            if not local_storage.exists(input_file_path):
                fs.download(from_path=input_file_path, to_path=input_file_path)
            with open(input_file_path, "rb") as input_f:
                mime_type = local_storage.mime_type(path=input_file_path)
                files = {"file": (input_file_path, input_f, mime_type)}
                response = UnstructuredHelper.make_request(
                    unstructured_adapter_config=unstructured_adapter_config,
                    request_type=UnstructuredHelper.PROCESS,
                    files=files,
                )
            output, is_success = X2TextHelper.parse_response(
                response=response, out_file_path=output_file_path, fs=fs
            )
            if not is_success:
                raise AdapterError("Couldn't extract text from file")
            return output
        except OSError as e:
            msg = f"OS error while reading {input_file_path} "
            if output_file_path:
                msg += f"and writing {output_file_path}"
            msg += f": {str(e)}"
            logger.error(msg)
            raise AdapterError(str(e))

    @staticmethod
    def make_request(
        unstructured_adapter_config: dict[str, Any],
        request_type: str,
        **kwargs: dict[Any, Any],
    ) -> Response:
        unstructured_url = unstructured_adapter_config.get(UnstructuredHelper.URL)

        x2text_service_url = unstructured_adapter_config.get(X2TextConstants.X2TEXT_HOST)
        x2text_service_port = unstructured_adapter_config.get(X2TextConstants.X2TEXT_PORT)
        platform_service_api_key = unstructured_adapter_config.get(
            X2TextConstants.PLATFORM_SERVICE_API_KEY
        )
        headers = {
            "accept": MimeType.JSON,
            "Authorization": f"Bearer {platform_service_api_key}",
        }
        body = {
            "unstructured-url": unstructured_url,
        }
        # Add api key only if present
        api_key = unstructured_adapter_config.get(UnstructuredHelper.API_KEY)
        if api_key:
            body["unstructured-api-key"] = api_key

        x2text_url = (
            f"{x2text_service_url}:{x2text_service_port}" f"/api/v1/x2text/{request_type}"
        )
        # Add files only if the request is for process
        files = None
        if "files" in kwargs:
            files = kwargs["files"] if kwargs["files"] is not None else None
        try:
            response = requests.post(x2text_url, headers=headers, data=body, files=files)
            response.raise_for_status()
        except ConnectionError as e:
            logger.error(f"Adapter error: {e}")
            raise AdapterError(
                "Unable to connect to unstructured-io's service, " "please check the URL"
            )
        except Timeout as e:
            msg = "Request to unstructured-io's service has timed out"
            logger.error(f"{msg}: {e}")
            raise AdapterError(msg)
        except HTTPError as e:
            logger.error(f"Adapter error: {e}")
            default_err = "Error while calling the unstructured-io service"
            msg = AdapterUtils.get_msg_from_request_exc(
                err=e, message_key="detail", default_err=default_err
            )
            raise AdapterError("unstructured-io: " + msg)
        return response
