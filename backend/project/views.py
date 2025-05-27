import logging
from typing import Any

from account.custom_exceptions import DuplicateData
from connector.connector_instance_helper import ConnectorInstanceHelper
from django.conf import settings
from django.db import IntegrityError
from django.db.models import QuerySet
from django.http import HttpRequest
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

from project.constants import ProjectErrors

from .models import Project
from .serializers import ProjectSerializer

logger = logging.getLogger(__name__)


class ProjectViewSet(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = Project.objects.all()
    serializer_class = ProjectSerializer

    def get_queryset(self) -> QuerySet | None:
        created_by = self.request.query_params.get("created_by")
        if created_by is not None:
            queryset = Project.objects.filter(created_by=created_by)
            return queryset
        elif created_by is None:
            queryset = Project.objects.all()
            return queryset

    def create(
        self, request: HttpRequest, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        serializer = self.get_serializer(data=request.data)
        # Overriding default exception behavior
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise DuplicateData(
                f"{ProjectErrors.PROJECT_NAME_EXISTS}, {ProjectErrors.DUPLICATE_API}"
            )
        # Access the created instance
        created_instance: Project = serializer.instance

        # Enable GCS configurations to create GCS while creating a workflow
        if (
            settings.GOOGLE_STORAGE_ACCESS_KEY_ID
            and settings.UNSTRACT_FREE_STORAGE_BUCKET_NAME
        ):
            ConnectorInstanceHelper.create_default_gcs_connector(
                created_instance, request.user
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)
