import logging
from typing import Any, Optional
from urllib.parse import urlencode

from api_v2.api_key_validator import BaseAPIKeyValidator
from api_v2.exceptions import (
    ApiKeyCreateException,
    APINotFound,
    InactiveAPI,
    InvalidAPIRequest,
)
from api_v2.key_helper import KeyHelper
from api_v2.models import APIDeployment, APIKey
from api_v2.serializers import APIExecutionResponseSerializer
from api_v2.utils import APIDeploymentUtils
from django.core.files.uploadedfile import UploadedFile
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
        kwargs["api"] = api_deployment
        return func(self, request, *args, **kwargs)

    @staticmethod
    def validate_api(api_deployment: Optional[APIDeployment], api_key: str) -> None:
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
        model."""
        return WorkflowHelper.get_workflow_by_id(workflow_id)

    @staticmethod
    def get_api_by_id(api_id: str) -> Optional[APIDeployment]:
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
    ) -> Optional[APIDeployment]:
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
    ) -> ReturnDict:
        """Execute workflow by api.

        Args:
            organization_name (str): organization name
            api (APIDeployment): api model object
            file_obj (UploadedFile): input file
            use_file_history (bool): Use FileHistory table to return results on already
                processed files. Defaults to False
            tag_names (list(str)): list of tag names

        Returns:
            ReturnDict: execution status/ result
        """
        workflow_id = api.workflow.id
        pipeline_id = api.id
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
            )
            result.status_api = DeploymentHelper.construct_status_endpoint(
                api_endpoint=api.api_endpoint, execution_id=execution_id
            )
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
