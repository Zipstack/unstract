from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.permission import PromptAcesssToUser
from prompt_studio.prompt_studio_v2.constants import ToolStudioPromptKeys
from prompt_studio.prompt_studio_v2.controller import PromptStudioController
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from prompt_studio.prompt_studio_v2.serializers import ToolStudioPromptSerializer


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
    permission_classes: list[type[PromptAcesssToUser]] = [PromptAcesssToUser]

    def get_queryset(self) -> QuerySet | None:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ToolStudioPromptKeys.TOOL_ID,
        )
        if filter_args:
            queryset = ToolStudioPrompt.objects.filter(**filter_args)
        else:
            queryset = ToolStudioPrompt.objects.all()
        return queryset

    @action(detail=True, methods=["post"])
    def reorder_prompts(self, request: Request) -> Response:
        """Reorder the sequence of prompts based on the provided data.

        Args:
            request (Request): The HTTP request containing the reorder data.

        Returns:
            Response: The HTTP response indicating the status of the reorder operation.
        """
        prompt_studio_controller = PromptStudioController()
        return prompt_studio_controller.reorder_prompts(request, ToolStudioPrompt)

    @action(detail=False, methods=["get"])
    def available_lookups(self, request: Request) -> Response:
        """Get lookup projects linked to a Prompt Studio project.

        Returns the list of lookup projects that are linked at the project level
        and can be assigned to individual prompts for enrichment.

        Query Parameters:
            tool_id: UUID of the Prompt Studio project (CustomTool)

        Returns:
            Response: List of available lookup projects with id, name, and is_ready status
        """
        tool_id = request.query_params.get("tool_id")
        if not tool_id:
            return Response(
                {"error": "tool_id query parameter is required"},
                status=400,
            )

        try:
            from lookup.models import PromptStudioLookupLink

            links = PromptStudioLookupLink.objects.filter(
                prompt_studio_project_id=tool_id
            ).select_related("lookup_project")

            available_lookups = [
                {
                    "id": str(link.lookup_project.id),
                    "name": link.lookup_project.name,
                    "is_ready": link.lookup_project.is_ready,
                }
                for link in links
                if link.lookup_project.is_active
            ]

            return Response(available_lookups)
        except ImportError:
            # Lookup app not installed
            return Response([])
        except Exception as e:
            return Response(
                {"error": f"Failed to fetch available lookups: {str(e)}"},
                status=500,
            )
