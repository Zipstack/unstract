from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.prompt_studio_document_manager_v2.serializers import (
    PromptStudioDocumentManagerSerializer,
)
from prompt_studio.prompt_studio_output_manager_v2.constants import (
    PromptStudioOutputManagerKeys,
)

from .models import DocumentManager


class PromptStudioDocumentManagerView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    serializer_class = PromptStudioDocumentManagerSerializer

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
        )
        queryset = None
        if filter_args:
            queryset = DocumentManager.objects.filter(**filter_args)

        return queryset
