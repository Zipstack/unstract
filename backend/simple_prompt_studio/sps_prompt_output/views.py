from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from typing import Optional

from django.db.models import QuerySet
from .models import SPSPromptOutput
from .serializers import SPSPromptOutputSerializer
from prompt_studio.prompt_studio_output_manager.constants import (
    PromptStudioOutputManagerKeys,
)
from utils.filtering import FilterHelper


class SPSPromptOutputView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = SPSPromptOutput.objects.all()
    serializer_class = SPSPromptOutputSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        queryset = SPSPromptOutput.objects.all()
        filter_args = FilterHelper.build_filter_args(
            self.request,
            PromptStudioOutputManagerKeys.TOOL_ID,
            PromptStudioOutputManagerKeys.PROMPT_ID,
            PromptStudioOutputManagerKeys.DOCUMENT_MANAGER,
            "prompt_output_id",
        )

        if filter_args:
            queryset = SPSPromptOutput.objects.filter(**filter_args)

        return queryset

