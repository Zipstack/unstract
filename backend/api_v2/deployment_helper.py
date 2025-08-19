import logging
import re
from io import BytesIO
from typing import Any
from urllib.parse import urlencode, urlparse

import requests
from configuration.models import Configuration
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, UploadedFile
from rest_framework.request import Request
from rest_framework.serializers import Serializer
from rest_framework.utils.serializer_helpers import ReturnDict
from tags.models import Tag
from utils.constants import Account, CeleryQueue
from utils.local_context import StateStore
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.workflow_v2.dto import ExecutionResponse
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

from api_v2.api_key_validator import BaseAPIKeyValidator
from api_v2.dto import DeploymentExecutionDTO
from api_v2.exceptions import (
    ApiKeyCreateException,
    APINotFound,
    InactiveAPI,
    InvalidAPIRequest,
    PresignedURLFetchError,
)
from api_v2.key_helper import KeyHelper
from api_v2.models import APIDeployment, APIKey
from api_v2.serializers import APIExecutionResponseSerializer
from api_v2.utils import APIDeploymentUtils

logger = logging.getLogger(__name__)

# Default maximum file size for presigned URLs (20MB)
DEFAULT_PRESIGNED_URL_MAX_FILE_SIZE_MB = 20


class DeploymentHelper(BaseAPIKeyValidator):
    @staticmethod
    def validate_parameters(request: Request, **kwargs: Any) -> None:
        """Validate api_name for API deployments."""
        api_name = kwargs.get("api_name") or request.data.get("api_name")
        org_name = kwargs.get("org_name") or request.data.get("org_name")
        if not api_name:
            raise InvalidAPIRequest("Missing params api_name")
        # Set organization in state store for API
        StateStore.set(Account.ORGANIZATION_ID, org_name)

    @staticmethod
    def validate_and_process(
        self: Any, request: Request, func: Any, api_key: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Fetch API deployment and validate API key."""
        api_name = kwargs.get("api_name") or request.data.get("api_name")
        api_deployment = DeploymentHelper.get_deployment_by_api_name(api_name=api_name)
        DeploymentHelper.validate_api(api_deployment=api_deployment, api_key=api_key)

        deployment_execution_dto = DeploymentExecutionDTO(
            api=api_deployment, api_key=api_key
        )
        kwargs["deployment_execution_dto"] = deployment_execution_dto
        return func(self, request, *args, **kwargs)

    @staticmethod
    def validate_api(api_deployment: APIDeployment | None, api_key: str) -> None:
        """Validating API and API key.

        Args:
            api_deployment (Optional[APIDeployment]): _description_
            api_key (str): _description_

        Raises:
            APINotFound: _description_
            InactiveAPI: _description_
        """
        if not api_deployment:
            raise APINotFound()
        if not api_deployment.is_active:
            raise InactiveAPI()
        KeyHelper.validate_api_key(api_key=api_key, instance=api_deployment)

    @staticmethod
    def validate_and_get_workflow(workflow_id: str) -> Workflow:
        """Validate that the specified workflow_id exists in the Workflow
        model.
        """
        return WorkflowHelper.get_workflow_by_id(workflow_id)

    @staticmethod
    def get_api_by_id(api_id: str) -> APIDeployment | None:
        return APIDeploymentUtils.get_api_by_id(api_id=api_id)

    @staticmethod
    def construct_status_endpoint(api_endpoint: str, execution_id: str) -> str:
        """Construct a complete status endpoint URL by appending the
        execution_id as a query parameter.

        Args:
            api_endpoint (str): The base API endpoint.
            execution_id (str): The execution ID to be included as
                a query parameter.

        Returns:
            str: The complete status endpoint URL.
        """
        query_parameters = urlencode({"execution_id": execution_id})
        complete_endpoint = f"/{api_endpoint}?{query_parameters}"
        return complete_endpoint

    @staticmethod
    def get_deployment_by_api_name(
        api_name: str,
    ) -> APIDeployment | None:
        """Get and return the APIDeployment object by api_name."""
        try:
            api: APIDeployment = APIDeployment.objects.get(api_name=api_name)
            return api
        except APIDeployment.DoesNotExist:
            return None

    @staticmethod
    def create_api_key(serializer: Serializer, request: Request) -> APIKey:
        """To make API key for an API.

        Args:
            serializer (Serializer): Request serializer

        Raises:
            ApiKeyCreateException: Exception
        """
        api_deployment: APIDeployment = serializer.instance
        try:
            api_key: APIKey = KeyHelper.create_api_key(api_deployment, request)
            return api_key
        except Exception as error:
            logger.error(f"Error while creating API key error: {str(error)}")
            api_deployment.delete()
            logger.info("Deleted the deployment instance")
            raise ApiKeyCreateException()

    @classmethod
    def execute_workflow(
        cls,
        organization_name: str,
        api: APIDeployment,
        file_objs: list[UploadedFile],
        timeout: int,
        include_metadata: bool = False,
        include_metrics: bool = False,
        use_file_history: bool = False,
        tag_names: list[str] = [],
        llm_profile_id: str | None = None,
        hitl_queue_name: str | None = None,
    ) -> ReturnDict:
        """Execute workflow by api.

        Args:
            organization_name (str): organization name
            api (APIDeployment): api model object
            file_obj (UploadedFile): input file
            use_file_history (bool): Use FileHistory table to return results on already
                processed files. Defaults to False
            tag_names (list(str)): list of tag names
            llm_profile_id (str, optional): LLM profile ID for overriding tool settings
            hitl_queue_name (str, optional): Custom queue name for manual review

        Returns:
            ReturnDict: execution status/ result
        """
        workflow_id = api.workflow.id
        pipeline_id = api.id
        if hitl_queue_name:
            logger.info(
                f"API execution with HITL: hitl_queue_name={hitl_queue_name}, api_name={api.api_name}"
            )
        tags = Tag.bulk_get_or_create(tag_names=tag_names)
        workflow_execution = WorkflowExecutionServiceHelper.create_workflow_execution(
            workflow_id=workflow_id,
            pipeline_id=pipeline_id,
            mode=WorkflowExecution.Mode.QUEUE,
            tags=tags,
            total_files=len(file_objs),
        )
        execution_id = workflow_execution.id

        hash_values_of_files = SourceConnector.add_input_file_to_api_storage(
            pipeline_id=pipeline_id,
            workflow_id=workflow_id,
            execution_id=execution_id,
            file_objs=file_objs,
            use_file_history=use_file_history,
        )
        try:
            result = WorkflowHelper.execute_workflow_async(
                workflow_id=workflow_id,
                pipeline_id=pipeline_id,
                hash_values_of_files=hash_values_of_files,
                timeout=timeout,
                execution_id=execution_id,
                queue=CeleryQueue.CELERY_API_DEPLOYMENTS,
                use_file_history=use_file_history,
                llm_profile_id=llm_profile_id,
                hitl_queue_name=hitl_queue_name,
            )
            result.status_api = DeploymentHelper.construct_status_endpoint(
                api_endpoint=api.api_endpoint, execution_id=execution_id
            )
            # Check if highlight data should be removed using configuration registry
            organization = api.organization if api else None
            enable_highlight = False  # Safe default if the key is unavailable (e.g., OSS)
            from configuration.config_registry import ConfigurationRegistry

            if ConfigurationRegistry.is_config_key_available(
                "ENABLE_HIGHLIGHT_API_DEPLOYMENT"
            ):
                enable_highlight = Configuration.get_value_by_organization(
                    config_key="ENABLE_HIGHLIGHT_API_DEPLOYMENT",
                    organization=organization,
                )
            if not enable_highlight:
                result.remove_result_metadata_keys(["highlight_data"])
            if not include_metadata:
                result.remove_result_metadata_keys()
            if not include_metrics:
                result.remove_result_metrics()
        except Exception as error:
            DestinationConnector.delete_api_storage_dir(
                workflow_id=workflow_id, execution_id=execution_id
            )
            result = ExecutionResponse(
                workflow_id=workflow_id,
                execution_id=execution_id,
                execution_status=ExecutionStatus.ERROR.value,
                error=str(error),
            )
        return APIExecutionResponseSerializer(result).data

    @staticmethod
    def get_execution_status(execution_id: str) -> ExecutionResponse:
        """Current status of api execution.

        Args:
            execution_id (str): execution id

        Returns:
            ReturnDict: status/result of execution
        """
        execution_response: ExecutionResponse = WorkflowHelper.get_status_of_async_task(
            execution_id=execution_id
        )
        return execution_response

    @staticmethod
    def fetch_presigned_file(url: str) -> InMemoryUploadedFile:
        """Fetch a file from a presigned URL and convert it to an uploaded file.

        Args:
            url (str): The presigned URL to fetch the file from

        Returns:
            InMemoryUploadedFile: The fetched file as an uploaded file object

        Raises:
            PresignedURLFetchError: If the file cannot be fetched
        """
        # Basic SSRF protection: allow only HTTPS S3 endpoints
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme.lower()
        host = (parsed_url.hostname or "").lower()

        # Redact query string for safe logging and error messages
        sanitized_url = parsed_url._replace(query="").geturl()

        if scheme != "https":
            raise PresignedURLFetchError(
                url=sanitized_url, error_message="Only HTTPS presigned URLs are allowed"
            )

        # Check if this is an AWS S3 endpoint
        is_aws = host.endswith(".amazonaws.com")
        # Accept common S3 endpoint patterns: path-style, virtual-hosted, regional, dualstack, accelerated
        looks_like_s3 = (
            host == "s3.amazonaws.com"
            or host.endswith(".s3.amazonaws.com")
            or re.match(r"(^|.*\.)s3[.-]([a-z0-9-]+)\.amazonaws\.com$", host) is not None
        )

        if not (is_aws and looks_like_s3):
            raise PresignedURLFetchError(
                url=sanitized_url,
                error_message="URL host is not a valid S3 endpoint, only S3's pre-signed URLs are supported currently",
            )

        # Get file size limit from settings
        try:
            max_mb = getattr(
                settings,
                "API_DEPL_PRESIGNED_URL_MAX_FILE_SIZE_MB",
                DEFAULT_PRESIGNED_URL_MAX_FILE_SIZE_MB,
            )
            max_bytes = int(max_mb) * 1024 * 1024
        except Exception:
            max_bytes = (
                DEFAULT_PRESIGNED_URL_MAX_FILE_SIZE_MB * 1024 * 1024
            )  # sane default if settings unavailable

        file_stream = BytesIO()
        downloaded = 0
        content_type = ""  # Default content type

        try:
            # Request with timeouts, streaming, and no redirects
            with requests.get(
                url, stream=True, timeout=(5, 30), allow_redirects=False
            ) as resp:
                resp.raise_for_status()

                # Store content type for later use
                content_type = resp.headers.get("Content-Type", "")

                # Check Content-Length header if available
                content_length = resp.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > max_bytes:
                            raise PresignedURLFetchError(
                                url=sanitized_url,
                                error_message=f"File too large ({content_length} bytes). Max allowed: {max_bytes} bytes",
                            )
                    except ValueError:
                        # Non-integer Content-Length; ignore and fall back to stream enforcement
                        pass

                # Stream the body with an upper bound to prevent memory exhaustion
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    if not chunk:
                        continue

                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise PresignedURLFetchError(
                            url=sanitized_url,
                            error_message=f"File exceeds maximum allowed size of {max_bytes} bytes",
                        )

                    file_stream.write(chunk)

                # Reset stream position to beginning for reading
                file_stream.seek(0)

            # Extract filename from URL path
            filename = (
                parsed_url.path.split("/")[-1] if parsed_url.path else "unknown_file"
            )

            # If content type is generic or not set, use octet-stream
            if content_type in [
                "",
                "application/octet-stream",
                "binary/octet-stream",
            ]:
                content_type = "application/octet-stream"
                logger.warning(
                    f"Could not detect MIME type for file '{filename}' from URL '{sanitized_url}'"
                )

            logger.info(
                f"Fetched file '{filename}' with MIME type '{content_type}' from presigned URL {sanitized_url}"
            )

            return InMemoryUploadedFile(
                file=file_stream,
                field_name="file",
                name=filename,
                content_type=content_type,
                size=downloaded,
                charset=None,
            )

        except requests.RequestException as e:
            # Close the file stream on error
            if file_stream:
                file_stream.close()
            raise PresignedURLFetchError(url=sanitized_url, error_message=str(e))

    @staticmethod
    def load_presigned_files_generator(presigned_urls: list[str]):
        """Generator that yields files from presigned URLs one by one.

        Args:
            presigned_urls (list[str]): List of presigned URLs to fetch files from

        Yields:
            InMemoryUploadedFile: Each fetched file as an uploaded file object
        """
        for url in presigned_urls:
            yield DeploymentHelper.fetch_presigned_file(url)

    @staticmethod
    def load_presigned_files(
        presigned_urls: list[str], file_objs: list[InMemoryUploadedFile]
    ) -> None:
        """Load files from presigned URLs using a memory-efficient generator pattern.

        Args:
            presigned_urls (list[str]): List of presigned URLs to fetch files from
            file_objs (list[InMemoryUploadedFile]): List to append the fetched files to
        """
        for uploaded_file in DeploymentHelper.load_presigned_files_generator(
            presigned_urls
        ):
            file_objs.append(uploaded_file)
