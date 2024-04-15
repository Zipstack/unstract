from connector.constants import ConnectorInstanceKey as CIKey
from connector_processor.connector_processor import ConnectorProcessor
from connector_processor.constants import ConnectorKeys
from connector_processor.exceptions import IdIsMandatory, InValidType
from connector_processor.serializers import TestConnectorSerializer
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import Serializer
from rest_framework.versioning import URLPathVersioning
from rest_framework.viewsets import GenericViewSet


@api_view(("GET",))
def get_connector_schema(request: HttpRequest) -> HttpResponse:
    if request.method == "GET":
        connector_name = request.GET.get(ConnectorKeys.ID)
        if connector_name is None or connector_name == "":
            raise IdIsMandatory()
        json_schema = ConnectorProcessor.get_json_schema(connector_id=connector_name)
        return Response(data=json_schema, status=status.HTTP_200_OK)


@api_view(("GET",))
def get_supported_connectors(request: HttpRequest) -> HttpResponse:
    """Retrieves a list of supported connectors based on the provided connector
    type and mode.

    Args:
        request (HttpRequest): The HTTP request object.

    Returns:
        HttpResponse: The HTTP response containing the list of supported
        connectors in JSON format.
    """
    if request.method == "GET":
        connector_type = request.GET.get(ConnectorKeys.TYPE)
        connector_mode = request.GET.get(ConnectorKeys.CONNECTOR_MODE)
        if connector_mode:
            connector_mode = ConnectorProcessor.validate_connector_mode(connector_mode)

        if (
            connector_type == ConnectorKeys.INPUT
            or connector_type == ConnectorKeys.OUTPUT
        ):
            json_schema = ConnectorProcessor.get_all_supported_connectors(
                type=connector_type, connector_mode=connector_mode
            )
            return Response(json_schema, status=status.HTTP_200_OK)
        else:
            raise InValidType


class ConnectorViewSet(GenericViewSet):
    versioning_class = URLPathVersioning
    serializer_class = TestConnectorSerializer

    def get_serializer_class(self) -> Serializer:
        if self.action == "test":
            return TestConnectorSerializer
        return super().get_serializer_class()

    def test(self, request: Request) -> Response:
        """Tests the connector against the credentials passed."""
        serializer: TestConnectorSerializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        connector_id = serializer.validated_data.get(ConnectorKeys.CONNECTOR_ID)
        cred_string = serializer.validated_data.get(CIKey.CONNECTOR_METADATA)
        test_result = ConnectorProcessor.test_connectors(
            connector_id=connector_id, cred_string=cred_string
        )
        return Response(
            {ConnectorKeys.IS_VALID: test_result},
            status=status.HTTP_200_OK,
        )
