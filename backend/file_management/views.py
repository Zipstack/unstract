import logging
import os
from typing import Any

from connector.models import ConnectorInstance
from django.http import HttpRequest
from file_management.exceptions import (
    ConnectorInstanceNotFound,
    ConnectorOAuthError,
    FileListError,
    InternalServerError,
)
from file_management.file_management_helper import FileManagerHelper
from file_management.serializer import (
    FileInfoIdeSerializer,
    FileInfoSerializer,
    FileListRequestIdeSerializer,
    FileListRequestSerializer,
    FileUploadIdeSerializer,
    FileUploadSerializer,
)
from oauth2client.client import HttpAccessTokenRefreshError
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from unstract.connectors.exceptions import ConnectorError
from unstract.connectors.filesystems.local_storage.local_storage import (
    LocalStorageFS,
)

logger = logging.getLogger(__name__)


class FileManagementViewSet(viewsets.ModelViewSet):
    """FileManagement view.

    Handles GET,POST,PUT,PATCH and DELETE
    """

    versioning_class = URLPathVersioning
    queryset = ConnectorInstance.objects.all()

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
            connector_instance: ConnectorInstance = (
                ConnectorInstance.objects.get(pk=id)
            )
            file_system = FileManagerHelper.get_file_system(connector_instance)
            files = FileManagerHelper.list_files(file_system, path)
            serializer = FileInfoSerializer(files, many=True)
            return Response(serializer.data)
        except ConnectorInstance.DoesNotExist:
            raise ConnectorInstanceNotFound()
        except HttpAccessTokenRefreshError as error:
            logger.error(
                f"HttpAccessTokenRefreshError thrown\
                        from file list, error {error}"
            )
            raise ConnectorOAuthError()
        except ConnectorError as error:
            logger.error(
                f"ConnectorError thrown during file list, error {error}"
            )
            raise FileListError(core_err=error)
        except Exception as error:
            logger.error(f"Exception thrown from file list, error {error}")
            raise InternalServerError()

    @action(detail=True, methods=["get"])
    def download(self, request: HttpRequest) -> Response:
        serializer = FileListRequestSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        id: str = serializer.validated_data.get("connector_id")
        path: str = serializer.validated_data.get("path")
        connector_instance: ConnectorInstance = ConnectorInstance.objects.get(
            pk=id
        )
        file_system = FileManagerHelper.get_file_system(connector_instance)
        return FileManagerHelper.download_file(file_system, path)

    @action(detail=True, methods=["post"])
    def upload(self, request: HttpRequest) -> Response:
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        id: str = serializer.validated_data.get("connector_id")

        path: str = serializer.validated_data.get("path")
        uploaded_files: Any = serializer.validated_data.get("file")
        connector_instance: ConnectorInstance = ConnectorInstance.objects.get(
            pk=id
        )
        file_system = FileManagerHelper.get_file_system(connector_instance)

        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            logger.info(
                f"Uploading file: {file_name}"
                if file_name
                else "Uploading file"
            )
            FileManagerHelper.upload_file(
                file_system, path, uploaded_file, file_name
            )
        return Response({"message": "Files are uploaded successfully!"})

    @action(detail=True, methods=["post"])
    def upload_for_ide(self, request: HttpRequest) -> Response:
        print(request.data)
        serializer = FileUploadIdeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded_files: Any = serializer.validated_data.get("file")
        tool_id: str = request.query_params.get("tool_id")
        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            request.org_id,
            is_create=True,
            user_id=request.user.user_id,
            tool_id=tool_id,
        )
        file_system = LocalStorageFS(settings={"path": file_path})
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            logger.info(
                f"Uploading file: {file_name}"
                if file_name
                else "Uploading file"
            )
            FileManagerHelper.upload_file(
                file_system,
                file_path,
                uploaded_file,
                file_name,
            )
        return Response({"message": "Files are uploaded successfully!"})

    @action(detail=True, methods=["get"])
    def fetch_contents_ide(self, request: HttpRequest) -> Response:
        serializer = FileInfoIdeSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        file_name: str = serializer.validated_data.get("file_name")
        tool_id: str = serializer.validated_data.get("tool_id")
        file_path = (
            file_path
        ) = FileManagerHelper.handle_sub_directory_for_tenants(
            request.org_id,
            is_create=True,
            user_id=request.user.user_id,
            tool_id=tool_id,
        )
        file_system = LocalStorageFS(settings={"path": file_path})
        if not file_path.endswith("/"):
            file_path += "/"
        file_path += file_name
        contents = FileManagerHelper.fetch_file_contents(file_system, file_path)
        return Response({"data": contents}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def list_ide(self, request: HttpRequest) -> Response:
        serializer = FileListRequestIdeSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        tool_id: str = serializer.validated_data.get("tool_id")
        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            request.org_id,
            is_create=True,
            user_id=request.user.user_id,
            tool_id=tool_id,
        )
        file_system = LocalStorageFS(settings={"path": file_path})
        try:
            files = FileManagerHelper.list_files(file_system, file_path)
            serializer = FileInfoSerializer(files, many=True)
            # fetching only the name from path
            for file in serializer.data:
                file_name = os.path.basename(file.get("name"))
                file["name"] = file_name
            return Response(serializer.data)
        except Exception as error:
            logger.error(f"Exception thrown from file list, error {error}")
            raise InternalServerError()

    @action(detail=True, methods=["get"])
    def delete(self, request: HttpRequest) -> Response:
        serializer = FileInfoIdeSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        file_name: str = serializer.validated_data.get("file_name")
        tool_id: str = serializer.validated_data.get("tool_id")
        file_path = FileManagerHelper.handle_sub_directory_for_tenants(
            request.org_id,
            is_create=False,
            user_id=request.user.user_id,
            tool_id=tool_id,
        )
        path = file_path
        if not file_name:
            return Response(
                {"data": "File deletion failed. File name is mandatory"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        file_system = LocalStorageFS(settings={"path": path})
        try:
            FileManagerHelper.delete_file(file_system, path, file_name)
            return Response(
                {"data": "File deleted succesfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            logger.error(f"Exception thrown from file deletion, error {exc}")
            return Response(
                {"data": "File deletion failed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
