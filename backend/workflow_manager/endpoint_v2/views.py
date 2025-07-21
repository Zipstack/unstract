from django.db.models import QuerySet
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.endpoint_utils import WorkflowEndpointUtils
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.endpoint_v2.serializers import WorkflowEndpointSerializer
from workflow_manager.endpoint_v2.source import SourceConnector


class WorkflowEndpointViewSet(viewsets.ModelViewSet):
    serializer_class = WorkflowEndpointSerializer

    def get_queryset(self) -> QuerySet:
        queryset = (
            WorkflowEndpoint.objects.all()
            .select_related("workflow")
            .filter(workflow__created_by=self.request.user)
        )
        workflow_filter = self.request.query_params.get("workflow", None)
        if workflow_filter:
            queryset = queryset.filter(workflow_id=workflow_filter)

        endpoint_type_filter = self.request.query_params.get("endpoint_type", None)
        if endpoint_type_filter:
            queryset = queryset.filter(endpoint_type=endpoint_type_filter)

        connection_type_filter = self.request.query_params.get("connection_type", None)
        if connection_type_filter:
            queryset = queryset.filter(connection_type=connection_type_filter)
        return queryset

    @action(detail=True, methods=["get"])
    def get_settings(self, request: Request, pk: str) -> Response:
        """Retrieve the settings/schema for a specific workflow endpoint.

        Parameters:
            request (Request): The HTTP request object.
            pk (str): The primary key of the workflow endpoint.

        Returns:
            Response: The HTTP response containing the settings/schema for
                the endpoint.
        """
        endpoint: WorkflowEndpoint = self.get_object()
        connection_type = endpoint.connection_type
        endpoint_type = endpoint.endpoint_type
        schema = None
        if endpoint_type == WorkflowEndpoint.EndpointType.SOURCE:
            if connection_type == WorkflowEndpoint.ConnectionType.API:
                schema = SourceConnector.get_json_schema_for_api()
            if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
                schema = SourceConnector.get_json_schema_for_file_system()
        if endpoint_type == WorkflowEndpoint.EndpointType.DESTINATION:
            if connection_type == WorkflowEndpoint.ConnectionType.DATABASE:
                schema = DestinationConnector.get_json_schema_for_database()
            if connection_type == WorkflowEndpoint.ConnectionType.FILESYSTEM:
                schema = DestinationConnector.get_json_schema_for_file_system()
            if connection_type == WorkflowEndpoint.ConnectionType.API:
                schema = DestinationConnector.get_json_schema_for_api()

        return Response(
            {
                "status": status.HTTP_200_OK,
                "schema": schema,
            }
        )

    @action(detail=True, methods=["get"])
    def workflow_endpoint_list(self, request: Request, pk: str) -> Response:
        """Retrieve a list of endpoints for a specific workflow.

        Parameters:
            request (Request): The HTTP request object.
            pk (str): The primary key of the workflow.

        Returns:
            Response: The HTTP response containing the serialized list of
                endpoints.
        """
        endpoints = WorkflowEndpointUtils.get_endpoints_for_workflow(pk)
        serializer = WorkflowEndpointSerializer(endpoints, many=True)
        return Response(serializer.data)
