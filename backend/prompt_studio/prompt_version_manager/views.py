from permissions.permission import IsOwner
from prompt_studio.prompt_version_manager.helper import PromptVersionHelper
from prompt_studio.prompt_version_manager.serializers import (
    LoadVersionSerializer,
    PromptVersionManagerSerializer,
)
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning

from backend.pagination import DefaultPagination

from .models import PromptVersionManager


class PromptVersionManagerView(viewsets.ModelViewSet):
    """Viewset to handle all Custom tool related operations."""

    versioning_class = URLPathVersioning
    permission_classes = [IsOwner]
    queryset = PromptVersionManager.objects.all()
    serializer_class = PromptVersionManagerSerializer
    pagination_class = DefaultPagination

    def list(self, request, prompt_id, *args, **kwargs):
        queryset = self.get_queryset().filter(prompt_id=prompt_id).order_by("version")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def list_paginated(self, request, prompt_id, *args, **kwargs):
        """This function is to support pagination.

        Not used currently because pagination needs to be implemented in
        the frontend.
        """
        queryset = self.get_queryset().filter(prompt_id=prompt_id).order_by("version")
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def load_version(self, request, prompt_id):
        serializer = LoadVersionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                serializer.errors, status=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
        prompt_version = serializer.validated_data["prompt_version"]
        return PromptVersionHelper.load_prompt_version(
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )
