import logging
from typing import Optional

from django.db.models import QuerySet
from prompt_studio.prompt_studio_output_manager.constants import (
    PromptStudioOutputManagerKeys,
)
from prompt_studio.prompt_studio_output_manager.serializers import (
    PromptStudioOutputSerializer,
)
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from .models import PromptStudioOutputManager

logger = logging.getLogger(__name__)


class PromptStudioOutputView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = PromptStudioOutputManager.objects.all()
    serializer_class = PromptStudioOutputSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
            PromptStudioOutputManagerKeys.PROMPT_ID,
            PromptStudioOutputManagerKeys.PROFILE_MANAGER,
            PromptStudioOutputManagerKeys.DOCUMENT_MANAGER,
        )
        if filter_args:
            queryset = PromptStudioOutputManager.objects.filter(**filter_args)
        else:
            queryset = PromptStudioOutputManager.objects.all()
        return queryset
