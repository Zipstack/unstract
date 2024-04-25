import logging
from typing import Optional

from django.db.models import QuerySet
from prompt_studio.permission import PromptAcesssToUser
from prompt_studio.prompt_studio.constants import ToolStudioPromptKeys
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from .models import TagManager
from .serializers import PromptTagSerializer

logger = logging.getLogger(__name__)


class ToolStudioPromptTagView(viewsets.ModelViewSet):
    """Viewset to handle all Tool Studio prompt tag related APIs.

    Args:
        viewsets (_type_)
    """

    versioning_class = URLPathVersioning
    serializer_class = PromptTagSerializer
    permission_classes: list[type[PromptAcesssToUser]] = [PromptAcesssToUser]

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ToolStudioPromptKeys.TOOL_ID,
        )
        if filter_args:
            queryset = TagManager.objects.filter(**filter_args)
        else:
            queryset = TagManager.objects.all()
        return queryset
