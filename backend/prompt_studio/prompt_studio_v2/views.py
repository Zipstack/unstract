from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.permission import IsPromptParentToolOwner, PromptAcesssToUser
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_v2.constants import ToolStudioPromptKeys
from prompt_studio.prompt_studio_v2.controller import PromptStudioController
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt
from prompt_studio.prompt_studio_v2.serializers import (
    ToolStudioPromptListSerializer,
    ToolStudioPromptSerializer,
)


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

    def get_permissions(self) -> list[Any]:
        # Reads and edits honour project sharing (UN-3315); deleting a prompt
        # requires ownership of the parent tool, matching CustomToolViewSet,
        # whose own `destroy` is IsOwner-gated. The bulk `sync_prompts` route
        # there is IsOwner-gated too. A read_write API key still reaches both
        # -- see PromptAcesssToUser's docstring.
        if self.action == "destroy":
            return [IsPromptParentToolOwner()]
        return [PromptAcesssToUser()]

    def get_serializer_class(self):
        if self.action == "list":
            return ToolStudioPromptListSerializer
        return ToolStudioPromptSerializer

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

        Routed at the collection path (``prompt/reorder/``) with the target
        taken from ``prompt_id`` in the body, so DRF never calls
        ``get_object()`` and the viewset's permission class never fires. The
        check below is therefore made explicitly -- same shape as
        ``ToolInstanceViewSet.reorder``, which has the same collection-POST
        problem. Reordering is an *edit*, so it honours project sharing
        (UN-3315) rather than requiring ownership.

        Args:
            request (Request): The HTTP request containing the reorder data.

        Returns:
            Response: The HTTP response indicating the status of the reorder operation.
        """
        prompt_id = request.data.get(ToolStudioPromptKeys.PROMPT_ID)
        if not prompt_id:
            raise ValidationError({ToolStudioPromptKeys.PROMPT_ID: "This is required."})
        # ToolStudioPrompt carries no organization of its own -- it is a plain
        # BaseModel -- so scope through the parent tool, whose for_user()
        # queryset is org-bound. A cross-org or invisible id 404s here rather
        # than reaching the permission check.
        prompt = get_object_or_404(
            ToolStudioPrompt.objects.filter(
                tool_id__in=CustomTool.objects.for_user(request.user)
            ),
            pk=prompt_id,
        )
        self.check_object_permissions(request, prompt)

        prompt_studio_controller = PromptStudioController()
        return prompt_studio_controller.reorder_prompts(request, ToolStudioPrompt)
