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
