import logging

from apps.app_deployment.models import AppDeployment
from connector.models import ConnectorInstance
from django.http import HttpRequest, HttpResponse
from file_management.exceptions import (
    ConnectorInstanceNotFound,
    ConnectorOAuthError,
    FileListError,
    InternalServerError,
)
from file_management.file_management_dto import FileInformation
from file_management.file_management_helper import FileManagerHelper
from file_management.serializer import FileInfoSerializer
from oauth2client.client import HttpAccessTokenRefreshError
from rest_framework import viewsets
from rest_framework.response import Response
from unstract.connectors.exceptions import ConnectorError

from .exceptions import AppNotFound, ValidationError
from .serializer import FileListRequestSerializer, ViewFileRequestSerializer

logger = logging.getLogger(__name__)


class DocumentView(viewsets.ModelViewSet):
    """_summary_

    Args:
        viewsets (_type_): _description_
    """

    def list_files(self, request: HttpRequest) -> Response:
        """_summary_

        Args:
            request (Request): _description_

        Raises:
            ConnectorInstanceNotFound: _description_
            ConnectorOAuthError: _description_
            FileListError: _description_
            InternalServerError: _description_
            ValidationError: _description_

        Returns:
            Response: _description_
        """

        serializer = FileListRequestSerializer(data=request.GET)
        if serializer.is_valid():
            app_id: str = serializer.validated_data.get("app_id")
            dir_only: bool = serializer.validated_data.get("dir_only")
            limit: int = serializer.validated_data.get("limit")
            path: str = "/"
            try:
                queryset: AppDeployment = AppDeployment.objects.get(
                    id=app_id, is_active=True
                )
                if queryset:
                    files = DocumentView.fetch_files(
                        queryset.workflow, path, dir_only
                    )
                    serializer = FileInfoSerializer(
                        files[:limit], many=True
                    )
                    return Response(serializer.data)
            except AppDeployment.DoesNotExist:
                raise AppNotFound()
        else:
            raise ValidationError(serializer.errors)

    @staticmethod
    def fetch_files(
        workflow_id: str, path: str, dir_only: bool
    ) -> list[FileInformation]:
        """_summary_

        Args:
            workflow_id (str): _description_
            path (str): _description_

        Raises:
            ConnectorInstanceNotFound: _description_
            ConnectorOAuthError: _description_
            FileListError: _description_
            InternalServerError: _description_

        Returns:
            list[FileInformation]: _description_
        """
        try:
            connector_instance: ConnectorInstance = (
                ConnectorInstance.objects.get(workflow=workflow_id, connector_type="INPUT")
            )
            file_system: FileManagerHelper = FileManagerHelper.get_file_system(
                connector_instance
            )
            if dir_only:
                return FileManagerHelper.list_directories(file_system, path)
            return FileManagerHelper.list_files(file_system, path)
        except ConnectorInstance.DoesNotExist:
            raise ConnectorInstanceNotFound()
        except HttpAccessTokenRefreshError:
            raise ConnectorOAuthError()
        except ConnectorError as error:
            raise FileListError(core_err=error)
        except Exception:
            raise InternalServerError()

    def get_file(self, request: HttpRequest) -> HttpResponse:
        serializer = ViewFileRequestSerializer(data=request.GET)
        if serializer.is_valid():
            app_id: str = serializer.validated_data.get("app_id")
            file_name: str = serializer.validated_data.get("file_name")
            try:
                queryset: AppDeployment = AppDeployment.objects.get(
                    id=app_id, is_active=True
                )
                if queryset:
                    response: HttpResponse = DocumentView.get_file_content(
                        queryset.workflow, file_name
                    )
                    return response
            except AppDeployment.DoesNotExist:
                raise AppNotFound()
        else:
            raise ValidationError(serializer.errors)

    @staticmethod
    def get_file_content(workflow_id: str, file_name: str) -> HttpResponse:
        try:
            connector_instance: ConnectorInstance = (
                ConnectorInstance.objects.get(workflow=workflow_id, connector_type="INPUT")
            )
            file_system: FileManagerHelper = FileManagerHelper.get_file_system(
                connector_instance
            )
            return FileManagerHelper.download_file(file_system, file_name, True)
        except ConnectorInstance.DoesNotExist:
            raise ConnectorInstanceNotFound()
        except HttpAccessTokenRefreshError:
            raise ConnectorOAuthError()
        except ConnectorError as error:
            raise FileListError(core_err=error)
        except Exception:
            raise InternalServerError()
