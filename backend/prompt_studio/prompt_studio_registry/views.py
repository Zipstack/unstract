import logging
from typing import Optional

from django.db.models import QuerySet
from prompt_studio.prompt_studio_core.models import CustomTool
from prompt_studio.prompt_studio_registry.constants import (
    PromptStudioRegistryKeys,
)
from prompt_studio.prompt_studio_registry.exceptions import ToolDoesNotExist
from prompt_studio.prompt_studio_registry.prompt_studio_registry_helper import (
    PromptStudioRegistryHelper,
)
from prompt_studio.prompt_studio_registry.serializers import (
    ExportToolRequestSerializer,
    PromptStudioRegistrySerializer,
)
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from .models import PromptStudioRegistry

logger = logging.getLogger(__name__)


class PromptStudioRegistryView(viewsets.ModelViewSet):
    """Driver class to handle export and registering of custom tools to private
    tool hub."""

    versioning_class = URLPathVersioning
    queryset = PromptStudioRegistry.objects.all()
    serializer_class = PromptStudioRegistrySerializer

    def get_queryset(self) -> Optional[QuerySet]:
        filterArgs = FilterHelper.build_filter_args(
            self.request,
            PromptStudioRegistryKeys.PROMPT_REGISTRY_ID,
        )
        if filterArgs:
            queryset = PromptStudioRegistry.objects.filter(**filterArgs)
        else:
            queryset = PromptStudioRegistry.objects.all()
        return queryset

    @action(detail=True, methods=["get"])
    def export_tool(self, request: Request) -> Response:
        """API Endpoint for exporting required jsons for the custom tool."""
        serializer = ExportToolRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        custom_tool_id = serializer.validated_data.get(
            PromptStudioRegistryKeys.PROMPT_REGISTRY_ID
        )
        try:
            custom_tool = CustomTool.objects.get(tool_id=custom_tool_id)
        except CustomTool.DoesNotExist as error:
            logger.error(
                f"Error occured while fetching tool \
                    for tool_id:{custom_tool_id} {error}"
            )
            raise ToolDoesNotExist from error
        PromptStudioRegistryHelper.update_or_create_psr_tool(custom_tool=custom_tool)
        return Response(
            {"message": "Custom tool exported sucessfully."},
            status=status.HTTP_200_OK,
        )
