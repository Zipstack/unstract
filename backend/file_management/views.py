import logging
from typing import Any

from connector_v2.models import ConnectorInstance
from django.http import HttpRequest
from oauth2client.client import HttpAccessTokenRefreshError
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

from file_management.exceptions import (
    ConnectorInstanceNotFound,
    ConnectorOAuthError,
    FileListError,
)
from file_management.file_management_helper import FileManagerHelper
from file_management.serializer import (
    FileInfoSerializer,
    FileListRequestSerializer,
    FileUploadSerializer,
)
from unstract.connectors.exceptions import ConnectorError

logger = logging.getLogger(__name__)


class FileManagementViewSet(viewsets.ModelViewSet):
    """FileManagement view."""

    versioning_class = URLPathVersioning

    def get_queryset(self):
        return ConnectorInstance.objects.all()

    def get_serializer_class(self) -> serializers.Serializer:
        if self.action == "upload":
            return FileUploadSerializer
        elif self.action == "download":
            return FileListRequestSerializer
        else:
            # Default serializer class
            return FileListRequestSerializer

    def list(self, request: HttpRequest) -> Response:
        serializer = FileListRequestSerializer(data=request.GET)

        serializer.is_valid(raise_exception=True)
        # Query params
        id: str = serializer.validated_data.get("connector_id")
        path: str = serializer.validated_data.get("path")
        try:
            connector_instance: ConnectorInstance = ConnectorInstance.objects.get(pk=id)
            file_system = FileManagerHelper.get_file_system(connector_instance)
            files = FileManagerHelper.list_files(file_system, path)
            serializer = FileInfoSerializer(files, many=True)
            return Response(serializer.data)
        except ConnectorInstance.DoesNotExist:
            raise ConnectorInstanceNotFound()
        except HttpAccessTokenRefreshError as error:
            logger.error(
                f"HttpAccessTokenRefreshError thrown from file list, error {error}"
            )
            raise ConnectorOAuthError()
        except ConnectorError as error:
            logger.error(f"ConnectorError thrown during file list, error {error}")
            raise FileListError(core_err=error)

    @action(detail=True, methods=["get"])
    def download(self, request: HttpRequest) -> Response:
        serializer = FileListRequestSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        id: str = serializer.validated_data.get("connector_id")
        path: str = serializer.validated_data.get("path")
        connector_instance: ConnectorInstance = ConnectorInstance.objects.get(pk=id)
        file_system = FileManagerHelper.get_file_system(connector_instance)
        return FileManagerHelper.download_file(file_system, path)

    @action(detail=True, methods=["post"])
    def upload(self, request: HttpRequest) -> Response:
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        id: str = serializer.validated_data.get("connector_id")

        path: str = serializer.validated_data.get("path")
        uploaded_files: Any = serializer.validated_data.get("file")
        connector_instance: ConnectorInstance = ConnectorInstance.objects.get(pk=id)
        file_system = FileManagerHelper.get_file_system(connector_instance)

        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            logger.info(f"Uploading file: {file_name}" if file_name else "Uploading file")
            FileManagerHelper.upload_file(file_system, path, uploaded_file, file_name)
        return Response({"message": "Files are uploaded successfully!"})
