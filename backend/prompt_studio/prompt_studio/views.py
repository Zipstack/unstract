import logging
from typing import Optional

from django.db.models import QuerySet
from prompt_studio.prompt_studio.constants import ToolStudioPromptKeys
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from .models import ToolStudioPrompt
from .serializers import ToolStudioPromptSerializer

logger = logging.getLogger(__name__)


class ToolStudioPromptView(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt related API logics.

    Args:
        viewsets (_type_)

    Raises:
        DuplicateData
        FilenameMissingError
        IndexingError
        ValidationError
    """

    versioning_class = URLPathVersioning
    serializer_class = ToolStudioPromptSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ToolStudioPromptKeys.TOOL_ID,
        )
        if filter_args:
            queryset = ToolStudioPrompt.objects.filter(**filter_args)
        else:
            queryset = ToolStudioPrompt.objects.all()
        return queryset
