from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

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
            # index_status reads both relations for every row.
            queryset = (
                DocumentManager.objects.filter(**filter_args)
                .select_related("tool")
                .prefetch_related("index_managers", "tool__profile_managers")
            )

        return queryset
