from typing import Any

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
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
        # Reads and edits honour project sharing (UN-3315), enforced on two
        # levels: get_queryset scopes every action to the user's reachable
        # tools, and these classes gate the object. Deleting a prompt requires
        # ownership of the parent tool, matching CustomToolViewSet, whose own
        # `destroy` is IsOwner-gated. The bulk `sync_prompts` route there is
        # IsOwner-gated too. API-key gap: see PromptAcesssToUser.
        if self.action == "destroy":
            return [IsPromptParentToolOwner()]
        return [PromptAcesssToUser()]

    def get_serializer_class(self):
        if self.action == "list":
            return ToolStudioPromptListSerializer
        return ToolStudioPromptSerializer

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Gate a reparent on the parent the prompt is being moved OUT of.

        ``PromptAcesssToUser`` admits org-shared members here, but
        ``IsPromptParentToolOwner`` denies them ``destroy`` -- and that gate
        reads the *stored* parent, which DRF loads before the update is
        applied. So a writable ``tool_id`` let a denied user PATCH the prompt
        into a tool they own and then delete it legitimately, in two requests
        that each passed every check.

        Moving a prompt out of a project removes it from that project, which
        is a deletion from the losing side, so it requires what ``destroy``
        requires -- checked against the EXISTING parent, not the new one. A
        check against the new parent would pass trivially: the attacker's
        destination is a tool they already own, and the harm is the prompt
        leaving the original project regardless of where it lands.

        A no-op ``tool_id`` (unchanged) stays allowed, so the UI's field-level
        PATCH is unaffected. An owner reparenting between tools they own stays
        allowed. ``null`` is treated as a reparent, not a no-op: orphaning the
        row hides it from everyone, its owner and org admins included, once
        the org filter's INNER JOIN excludes it.

        This narrows the bypass; it does not make ``tool_id`` unwritable. The
        complete fix is a read-only field on update, which changes what the
        serializer accepts and was declined on API-contract grounds.
        """
        instance = self.get_object()
        if ToolStudioPromptKeys.TOOL_ID in request.data:
            requested = request.data[ToolStudioPromptKeys.TOOL_ID]
            current = instance.tool_id_id
            if requested is None or str(requested) != str(current):
                if not IsPromptParentToolOwner().has_object_permission(
                    request, self, instance
                ):
                    raise PermissionDenied(
                        "Moving a prompt out of its project requires ownership "
                        "of that project."
                    )
        return super().update(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet | None:
        # Scope to tools the user can reach. `list` never calls get_object(),
        # and neither permission class defines has_permission, so nothing
        # object-level fires on it -- unscoped, any org member could enumerate
        # every prompt in the organization. Both branches need this: the
        # filtered one takes tool_id straight from the query string with no
        # ownership check of its own, so it was equally open.
        #
        # ToolStudioPrompt has no organization field and no for_user manager,
        # so the scoping goes through the parent, exactly as reorder_prompts
        # does. for_user ORs in shared_to_org, so a shared member still
        # reaches the prompt and still gets a real 403 (not a 404) from
        # IsPromptParentToolOwner on destroy.
        visible = ToolStudioPrompt.objects.filter(
            tool_id__in=CustomTool.objects.for_user(self.request.user)
        )
        filter_args = FilterHelper.build_filter_args(
            self.request,
            ToolStudioPromptKeys.TOOL_ID,
        )
        return visible.filter(**filter_args) if filter_args else visible

    @action(detail=True, methods=["post"])
    def reorder_prompts(self, request: Request, **kwargs: Any) -> Response:
        """Reorder the sequence of prompts based on the provided data.

        ``**kwargs`` absorbs the ``format`` argument that
        ``format_suffix_patterns`` passes on the ``prompt/reorder.json``
        variant of this route; the bare signature raised ``TypeError`` (500)
        there. The DRF mixins take ``*args, **kwargs`` for the same reason.

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
        # than reaching the permission check. select_related because the
        # permission class immediately dereferences the tool_id FK, and the
        # parent is already joined by the filter above.
        prompt = get_object_or_404(
            ToolStudioPrompt.objects.filter(
                tool_id__in=CustomTool.objects.for_user(request.user)
            ).select_related("tool_id"),
            pk=prompt_id,
        )
        self.check_object_permissions(request, prompt)

        prompt_studio_controller = PromptStudioController()
        return prompt_studio_controller.reorder_prompts(request, ToolStudioPrompt)
