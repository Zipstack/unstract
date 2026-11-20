from typing import Any

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_document_manager_v2.serializers import (
    PromptStudioDocumentStatusSerializer,
)
from prompt_studio.prompt_studio_output_manager_v2.constants import (
    PromptStudioOutputManagerKeys,
)

from .models import DocumentManager


class PromptStudioDocumentManagerView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = PromptStudioDocumentStatusSerializer

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
        )
        queryset = None
        if filter_args:
            # index_status reads both relations per row.
            queryset = (
                DocumentManager.objects.filter(**filter_args)
                .select_related("tool")
                .prefetch_related("index_managers", "tool__profile_managers")
            )

        return queryset

    def get_serializer_context(self) -> dict[str, Any]:
        context = super().get_serializer_context()
        context["show_failure_reason"] = self._can_open_tool()
        return context

    def _can_open_tool(self) -> bool:
        """The failure reason is provider error text: only users who can open
        the tool see it. Everyone else still sees the failed status.
        """
        tool_id = self.request.query_params.get(PromptStudioOutputManagerKeys.TOOL_ID)
        if not tool_id:
            return False
        try:
            return (
                CustomTool.objects.for_user(self.request.user).filter(pk=tool_id).exists()
            )
        except ValidationError:
            return False
