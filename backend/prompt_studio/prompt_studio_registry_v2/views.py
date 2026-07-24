import logging
from typing import Any

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tool_instance_v2.models import ToolInstance
from utils.filtering import FilterHelper

from prompt_studio.permission import IsRegistryToolOwner
from prompt_studio.prompt_studio_registry_v2.constants import PromptStudioRegistryKeys
from prompt_studio.prompt_studio_registry_v2.serializers import (
    PromptStudioRegistrySerializer,
)

from .exceptions import RegistryToolInUseError
from .models import PromptStudioRegistry

logger = logging.getLogger(__name__)


class PromptStudioRegistryView(viewsets.ModelViewSet):
    """Driver class to handle export and registering of custom tools to private
    tool hub.
    """

    versioning_class = URLPathVersioning
    serializer_class = PromptStudioRegistrySerializer

    def get_permissions(self) -> list[Any]:
        # `list` stays as it was - visibility is already derived by
        # `list_tools`. Only the destructive detail route is gated.
        if self.action == "destroy":
            return [IsRegistryToolOwner()]
        return super().get_permissions()

    def get_queryset(self) -> QuerySet | None:
        # Detail routes address a single row by PK; the list filters below are
        # query-param driven and would resolve to None, breaking get_object().
        # Keyed off the URL kwarg rather than `self.detail`, which DRF only
        # populates for router-generated views (it is None under as_view()).
        if self.kwargs.get("pk"):
            return PromptStudioRegistry.objects.all()

        filterArgs = FilterHelper.build_filter_args(
            self.request,
            PromptStudioRegistryKeys.PROMPT_REGISTRY_ID,
            "custom_tool",
        )
        queryset = None
        if filterArgs:
            queryset = PromptStudioRegistry.objects.filter(**filterArgs)

        return queryset

    def destroy(
        self, request: Request, *args: tuple[Any], **kwargs: dict[str, Any]
    ) -> Response:
        """Unpublish an exported tool without deleting its Prompt Studio project.

        Deleting the project cascades to its registry entry, but that is a blunt
        instrument - it gives no way to unpublish a tool while keeping the
        project. Guarded by the same in-use check `prompt-studio delete`
        performs, so a tool still attached to a workflow is refused.
        """
        instance: PromptStudioRegistry = self.get_object()
        dependent_wfs = set(
            ToolInstance.objects.filter(tool_id=instance.pk)
            .values_list("workflow_id", flat=True)
            .distinct()
        )
        if dependent_wfs:
            logger.info(
                f"Cannot delete exported tool {instance.prompt_registry_id}, "
                f"depended by workflows {dependent_wfs}"
            )
            raise RegistryToolInUseError()
        return super().destroy(request, *args, **kwargs)
