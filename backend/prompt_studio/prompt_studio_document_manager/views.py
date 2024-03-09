from rest_framework import viewsets
from typing import Optional

from django.db.models import QuerySet

from prompt_studio.prompt_studio_document_manager.serializers import (
    PromptStudioDocumentManagerSerializer,
)
from prompt_studio.prompt_studio_output_manager.constants import (
    PromptStudioOutputManagerKeys,
)
from utils.filtering import FilterHelper
from .models import DocumentManager
from rest_framework.versioning import URLPathVersioning

class PromptStudioDocumentManagerView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = DocumentManager.objects.all()
    serializer_class = PromptStudioDocumentManagerSerializer
    
    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
        )
        if filter_args:
            queryset = DocumentManager.objects.filter(**filter_args)
        else:
            queryset = DocumentManager.objects.all()
        return queryset
    