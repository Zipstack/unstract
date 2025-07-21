import logging
import mimetypes
from io import BytesIO
from typing import Any
from urllib.parse import urlencode, urlparse

import requests
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
            if not settings.ENABLE_HIGHLIGHT_API_DEPLOYMENT:
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
        """Fetch a single file from a presigned URL.
        
        Args:
            url (str): The presigned URL to fetch the file from
            
        Returns:
            InMemoryUploadedFile: The fetched file as an uploaded file object
            
        Raises:
            PresignedURLFetchError: If the file cannot be fetched
        """
        try:
            resp = requests.get(url)
            resp.raise_for_status()
        except (requests.ConnectionError, requests.RequestException) as e:
            raise PresignedURLFetchError(url=url, error_message=str(e))

        # Extract filename using urlparse for better handling
        parsed_url = urlparse(url)
        filename = (
            parsed_url.path.split("/")[-1] if parsed_url.path else "unknown_file"
        )
        
        # Remove query parameters from filename if present
        if "?" in filename:
            filename = filename.split("?")[0]

        # Determine content type with better MIME type detection
        content_type = resp.headers.get("Content-Type", "")
        
        # If content type is generic or not set, try to detect from filename
        if not content_type or content_type in ["application/octet-stream", "binary/octet-stream"]:
            detected_type, _ = mimetypes.guess_type(filename)
            if detected_type:
                content_type = detected_type
                logger.info(f"Detected MIME type '{content_type}' for file '{filename}' from extension")
            else:
                # If we still can't detect the type, check for common patterns in URL
                if any(ext in url.lower() for ext in ['.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg']):
                    # Extract extension from URL path
                    for ext in ['.pdf', '.docx', '.xlsx', '.png', '.jpg', '.jpeg']:
                        if ext in url.lower():
                            temp_filename = f"file{ext}"
                            detected_type, _ = mimetypes.guess_type(temp_filename)
                            if detected_type:
                                content_type = detected_type
                                logger.info(f"Detected MIME type '{content_type}' from URL pattern '{ext}'")
                                break
                
                if content_type in ["", "application/octet-stream", "binary/octet-stream"]:
                    content_type = "application/octet-stream"
                    logger.warning(f"Could not detect MIME type for file '{filename}' from URL '{url}', using fallback")
        
        logger.info(f"Fetched file '{filename}' with MIME type '{content_type}' from presigned URL")

        file_stream = BytesIO(resp.content)
        uploaded_file = InMemoryUploadedFile(
            file=file_stream,
            field_name="file",
            name=filename,
            content_type=content_type,
            size=len(resp.content),
            charset=None,
        )
        return uploaded_file

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
        for uploaded_file in DeploymentHelper.load_presigned_files_generator(presigned_urls):
            file_objs.append(uploaded_file)
