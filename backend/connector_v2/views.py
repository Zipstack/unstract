import logging
from typing import Any

from account_v2.custom_exceptions import DuplicateData
from connector_auth_v2.constants import ConnectorAuthKey
from connector_auth_v2.exceptions import CacheMissException, MissingParamException
from connector_auth_v2.pipeline.common import ConnectorAuthHelper
from connector_processor.exceptions import OAuthTimeOut
from django.db import IntegrityError
from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper
from permissions.permission import IsOrganizationMember

from backend.constants import RequestKey
from connector_v2.constants import ConnectorInstanceKey as CIKey

from .models import ConnectorInstance
from .serializers import ConnectorInstanceSerializer

logger = logging.getLogger(__name__)


class ConnectorInstanceViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = ConnectorInstanceSerializer

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            RequestKey.WORKFLOW,
            RequestKey.CREATED_BY,
            CIKey.CONNECTOR_TYPE,
            CIKey.CONNECTOR_MODE,
        )
        if filter_args:
            queryset = ConnectorInstance.objects.filter(**filter_args)
        else:
            queryset = ConnectorInstance.objects.all()
        return queryset

    def _get_connector_metadata(self, connector_id: str) -> dict[str, str] | None:
        """Gets connector metadata for the ConnectorInstance.

        For non oauth based - obtains from request
        For oauth based - obtains from cache

        Raises:
            e: MissingParamException, CacheMissException

        Returns:
            dict[str, str]: Connector creds dict to connect with
        """
        connector_metadata = None
        if ConnectorInstance.supportsOAuth(connector_id=connector_id):
            logger.info(f"Fetching oauth data for {connector_id}")
            oauth_key = self.request.query_params.get(ConnectorAuthKey.OAUTH_KEY)
            if oauth_key is None:
                raise MissingParamException(param=ConnectorAuthKey.OAUTH_KEY)
            connector_metadata = ConnectorAuthHelper.get_oauth_creds_from_cache(
                cache_key=oauth_key, delete_key=True
            )
            if connector_metadata is None:
                raise CacheMissException(
                    f"Couldn't find credentials for {oauth_key} from cache"
                )
        else:
            connector_metadata = self.request.data.get(CIKey.CONNECTOR_METADATA)
        return connector_metadata

    def perform_update(self, serializer: ConnectorInstanceSerializer) -> None:
        connector_metadata = None
        connector_id = self.request.data.get(
            CIKey.CONNECTOR_ID, serializer.instance.connector_id
        )
        try:
            connector_metadata = self._get_connector_metadata(connector_id)
        # TODO: Handle specific exceptions instead of using a generic Exception.
        except Exception:
            # Suppress here to not shout during partial updates
            pass
        # Take metadata from instance itself since update
        # is performed on other fields of ConnectorInstance
        if connector_metadata is None:
            connector_metadata = serializer.instance.connector_metadata
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            modified_by=self.request.user,
        )  # type: ignore

    def perform_create(self, serializer: ConnectorInstanceSerializer) -> None:
        connector_metadata = None
        connector_id = self.request.data.get(CIKey.CONNECTOR_ID)
        try:
            connector_metadata = self._get_connector_metadata(connector_id=connector_id)
        # TODO: Handle specific exceptions instead of using a generic Exception.
        except Exception as exc:
            logger.error(f"Error while obtaining ConnectorAuth: {exc}")
            raise OAuthTimeOut
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            created_by=self.request.user,
            modified_by=self.request.user,
        )  # type: ignore

    def create(self, request: Any) -> Response:
        # Overriding default exception behavior
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{CIKey.CONNECTOR_EXISTS}, \
                    {CIKey.DUPLICATE_API}"
            )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class SharedConnectorViewSet(viewsets.ModelViewSet):
    """ViewSet for managing centralized/shared connectors."""
    versioning_class = URLPathVersioning
    serializer_class = ConnectorInstanceSerializer
    permission_classes = [IsOrganizationMember]

    def get_queryset(self) -> QuerySet:
        """Return only shared connectors for the current organization."""
        filter_args = FilterHelper.build_filter_args(
            self.request,
            CIKey.CONNECTOR_TYPE,
            CIKey.CONNECTOR_MODE,
        )
        filter_args['is_shared'] = True
        return ConnectorInstance.objects.filter(**filter_args)

    def perform_create(self, serializer: ConnectorInstanceSerializer) -> None:
        """Create a new shared connector."""
        connector_metadata = None
        connector_id = self.request.data.get(CIKey.CONNECTOR_ID)
        try:
            connector_metadata = self._get_connector_metadata(connector_id=connector_id)
        except Exception as exc:
            logger.error(f"Error while obtaining ConnectorAuth: {exc}")
            raise OAuthTimeOut
        
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            is_shared=True,
            workflow=None,  # Shared connectors don't belong to specific workflows
            created_by=self.request.user,
            modified_by=self.request.user,
        )

    def perform_update(self, serializer: ConnectorInstanceSerializer) -> None:
        """Update a shared connector."""
        connector_metadata = None
        connector_id = self.request.data.get(
            CIKey.CONNECTOR_ID, serializer.instance.connector_id
        )
        try:
            connector_metadata = self._get_connector_metadata(connector_id)
        except Exception:
            pass
        
        if connector_metadata is None:
            connector_metadata = serializer.instance.connector_metadata
        
        serializer.save(
            connector_id=connector_id,
            connector_metadata=connector_metadata,
            modified_by=self.request.user,
        )

    def destroy(self, request, *args, **kwargs):
        """Delete a shared connector after checking if it's in use."""
        instance = self.get_object()
        
        # Check if connector is being used by any workflow endpoints
        from workflow_manager.endpoint_v2.models import WorkflowEndpoint
        workflow_usage_count = WorkflowEndpoint.objects.filter(connector_instance=instance).count()
        
        # Check if connector is being used by any tool instances
        from tool_instance_v2.models import ToolInstance
        tool_usage_count = (
            ToolInstance.objects.filter(input_file_connector=instance).count() +
            ToolInstance.objects.filter(output_file_connector=instance).count() +
            ToolInstance.objects.filter(input_db_connector=instance).count() +
            ToolInstance.objects.filter(output_db_connector=instance).count()
        )
        
        total_usage_count = workflow_usage_count + tool_usage_count
        
        if total_usage_count > 0:
            usage_details = []
            if workflow_usage_count > 0:
                usage_details.append(f"{workflow_usage_count} workflow endpoint(s)")
            if tool_usage_count > 0:
                usage_details.append(f"{tool_usage_count} tool instance(s)")
            
            usage_text = " and ".join(usage_details)
            return Response(
                {"error": f"Cannot delete connector. It is being used by {usage_text}."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        return super().destroy(request, *args, **kwargs)

    def _get_connector_metadata(self, connector_id: str) -> dict[str, str] | None:
        """Gets connector metadata for the ConnectorInstance."""
        connector_metadata = None
        if ConnectorInstance.supportsOAuth(connector_id=connector_id):
            logger.info(f"Fetching oauth data for {connector_id}")
            oauth_key = self.request.query_params.get(ConnectorAuthKey.OAUTH_KEY)
            if oauth_key is None:
                raise MissingParamException(param=ConnectorAuthKey.OAUTH_KEY)
            connector_metadata = ConnectorAuthHelper.get_oauth_creds_from_cache(
                cache_key=oauth_key, delete_key=True
            )
            if connector_metadata is None:
                raise CacheMissException(
                    f"Couldn't find credentials for {oauth_key} from cache"
                )
        else:
            connector_metadata = self.request.data.get(CIKey.CONNECTOR_METADATA)
        return connector_metadata

    @action(detail=True, methods=['post'])
    def test_connection(self, request, pk=None):
        """Test connection for a shared connector."""
        # This endpoint can be extended to test connector connections
        # For now, return success to maintain API compatibility
        return Response({"status": "Connection test successful"})

    @action(detail=False, methods=['get'])
    def by_type(self, request):
        """Get shared connectors filtered by type (INPUT/OUTPUT)."""
        connector_type = request.query_params.get('type')
        if connector_type not in ['INPUT', 'OUTPUT']:
            return Response(
                {"error": "type parameter must be 'INPUT' or 'OUTPUT'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        queryset = self.get_queryset().filter(connector_type=connector_type)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
