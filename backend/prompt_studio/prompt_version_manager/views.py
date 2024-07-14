from permissions.permission import IsOwner
from prompt_studio.prompt_version_manager.helper import PromptVersionHelper
from prompt_studio.prompt_version_manager.serializers import (
    PromptVersionManagerSerializer,
)
from rest_framework import viewsets
from rest_framework.exceptions import ValidationError
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
        if not prompt_id:
            raise ValidationError("prompt_id is required")
        queryset = self.get_queryset().filter(prompt_id=prompt_id).order_by("version")
        paginator = self.pagination_class()
        paginated_queryset = paginator.paginate_queryset(queryset, request)
        serializer = self.get_serializer(paginated_queryset, many=True)
        return paginator.get_paginated_response(serializer.data)

    def load_version(self, request, prompt_id, prompt_version):
        return PromptVersionHelper.load_prompt_version(
            prompt_id=prompt_id,
            prompt_version=prompt_version,
        )

    def test(self, request):
        return Response("Success")
