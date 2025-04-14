import logging

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.prompt_studio_registry_v2.constants import PromptStudioRegistryKeys
from prompt_studio.prompt_studio_registry_v2.serializers import (
    PromptStudioRegistrySerializer,
)

from .models import PromptStudioRegistry

logger = logging.getLogger(__name__)


class PromptStudioRegistryView(viewsets.ModelViewSet):
    """Driver class to handle export and registering of custom tools to private
    tool hub.
    """

    versioning_class = URLPathVersioning
    serializer_class = PromptStudioRegistrySerializer

    def get_queryset(self) -> QuerySet | None:
        filterArgs = FilterHelper.build_filter_args(
            self.request,
            PromptStudioRegistryKeys.PROMPT_REGISTRY_ID,
        )
        queryset = None
        if filterArgs:
            queryset = PromptStudioRegistry.objects.filter(**filterArgs)

        return queryset
