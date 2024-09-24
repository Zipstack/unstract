import logging
import uuid
from functools import wraps
from typing import Any, Optional
from urllib.parse import urlencode

from api_v2.constants import ApiExecution
from api_v2.exceptions import (
    ApiKeyCreateException,
    APINotFound,
    Forbidden,
    InactiveAPI,
    UnauthorizedKey,
)
from api_v2.key_helper import KeyHelper
from api_v2.models import APIDeployment, APIKey
from api_v2.serializers import APIExecutionResponseSerializer
from django.core.files.uploadedfile import UploadedFile
from django.db import connection
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.utils.serializer_helpers import ReturnDict
from utils.constants import Account
from utils.local_context import StateStore
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.workflow_v2.dto import ExecutionResponse
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper

logger = logging.getLogger(__name__)


class DeploymentHelper:
    @staticmethod
    def validate_api_key(func: Any) -> Any:
        """Decorator that validates the API key.

        Sample header:
            Authorization: Bearer 123e4567-e89b-12d3-a456-426614174001
        Args:
            func (Any): Function to wrap for validation
        """

        @wraps(func)
        def wrapper(self: Any, request: Request, *args: Any, **kwargs: Any) -> Any:
            """Wrapper to validate the inputs and key.

            Args:
                request (Request): Request context

            Raises:
                Forbidden: _description_
                APINotFound: _description_

            Returns:
                Any: _description_
            """
            try:
                authorization_header = request.headers.get("Authorization")
                api_key = None
                if authorization_header and authorization_header.startswith("Bearer "):
                    api_key = authorization_header.split(" ")[1]
                if not api_key:
                    raise Forbidden("Missing api key")
                org_name = kwargs.get("org_name") or request.data.get("org_name")
                api_name = kwargs.get("api_name") or request.data.get("api_name")
                if not api_name:
                    raise Forbidden("Missing api_name")
                # Set organization in state store for API
                StateStore.set(Account.ORGANIZATION_ID, org_name)

                api_deployment = DeploymentHelper.get_deployment_by_api_name(
                    api_name=api_name
                )
                DeploymentHelper.validate_api(
                    api_deployment=api_deployment, api_key=api_key
                )
                kwargs["api"] = api_deployment
                return func(self, request, *args, **kwargs)

            except (UnauthorizedKey, InactiveAPI, APINotFound):
                raise
            except Exception as exception:
                logger.error(f"Exception: {exception}")
                return Response(
                    {"error": str(exception)}, status=status.HTTP_403_FORBIDDEN
                )

        return wrapper

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
        KeyHelper.validate_api_key(api_key=api_key, api_instance=api_deployment)

    @staticmethod
    def validate_and_get_workflow(workflow_id: str) -> Workflow:
        """Validate that the specified workflow_id exists in the Workflow
        model."""
        return WorkflowHelper.get_workflow_by_id(workflow_id)

    @staticmethod
    def get_api_by_id(api_id: str) -> Optional[APIDeployment]:
        try:
            api_deployment: APIDeployment = APIDeployment.objects.get(pk=api_id)
            return api_deployment
        except APIDeployment.DoesNotExist:
            return None

    @staticmethod
    def construct_complete_endpoint(api_name: str) -> str:
        """Constructs the complete API endpoint by appending organization
        schema, endpoint path, and Django app backend URL.

        Parameters:
        - endpoint (str): The endpoint path to be appended to the complete URL.

        Returns:
        - str: The complete API endpoint URL.
        """
        org_schema = connection.tenant.schema_name
        return f"{ApiExecution.PATH}/{org_schema}/{api_name}/"

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
    def create_api_key(serializer: Serializer) -> APIKey:
        """To make API key for an API.

        Args:
            serializer (Serializer): Request serializer

        Raises:
            ApiKeyCreateException: Exception
        """
        api_deployment: APIDeployment = serializer.instance
        try:
            api_key: APIKey = KeyHelper.create_api_key(api_deployment)
            return api_key
        except Exception as error:
            logger.error(f"Error while creating API key error: {str(error)}")
            api_deployment.delete()
            logger.info("Deleted the deployment instance")
            raise ApiKeyCreateException()

    @staticmethod
    def execute_workflow(
        organization_name: str,
        api: APIDeployment,
        file_objs: list[UploadedFile],
        timeout: int,
        include_metadata: bool = False,
    ) -> ReturnDict:
        """Execute workflow by api.

        Args:
            organization_name (str): organization name
            api (APIDeployment): api model object
            file_obj (UploadedFile): input file

        Returns:
            ReturnDict: execution status/ result
        """
        workflow_id = api.workflow.id
        pipeline_id = api.id
        execution_id = str(uuid.uuid4())
        hash_values_of_files = SourceConnector.add_input_file_to_api_storage(
            workflow_id=workflow_id,
            execution_id=execution_id,
            file_objs=file_objs,
        )
        try:
            result = WorkflowHelper.execute_workflow_async(
                workflow_id=workflow_id,
                pipeline_id=pipeline_id,
                hash_values_of_files=hash_values_of_files,
                timeout=timeout,
                execution_id=execution_id,
                include_metadata=include_metadata,
            )
            result.status_api = DeploymentHelper.construct_status_endpoint(
                api_endpoint=api.api_endpoint, execution_id=execution_id
            )
        except Exception:
            DestinationConnector.delete_api_storage_dir(
                workflow_id=workflow_id, execution_id=execution_id
            )
            raise
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
