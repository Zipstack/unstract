import heapq
import logging
from typing import Any

from django.db.models import QuerySet
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from utils.filtering import FilterHelper

from prompt_studio.permission import IsRegistryToolOwner
from prompt_studio.prompt_studio_registry_v2.constants import PromptStudioRegistryKeys
from prompt_studio.prompt_studio_registry_v2.serializers import (
    PromptStudioRegistrySerializer,
)
from prompt_studio.tool_usage import (
    dependent_workflow_ids,
    deployment_types_for,
    join_deployment_types,
)

from .exceptions import RegistryToolInUseError
from .models import PromptStudioRegistry

logger = logging.getLogger(__name__)

# Blocking workflow IDs are logged so an operator can find the rows; capped so
# a heavily-reused tool cannot emit an unbounded log line.
_LOGGED_WORKFLOW_LIMIT = 20


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

        Note that unpublishing is not reversible in place: re-exporting mints a
        fresh `prompt_registry_id` and does not carry over `shared_to_org` /
        `shared_users`, so anything holding the old UUID must be updated.

        The dependent workflow IDs are materialised rather than reduced to an
        `.exists()` -- they are what names the blocking deployments below, which
        is the difference between an actionable 409 and one the caller cannot
        act on.
        """
        instance: PromptStudioRegistry = self.get_object()
        self._refuse_if_in_use(instance)
        return super().destroy(request, *args, **kwargs)

    def _refuse_if_in_use(self, instance: PromptStudioRegistry) -> None:
        """Raise a 409 naming the blockers when workflows still use ``instance``.

        Split from ``destroy`` so the guard can be exercised without standing
        up DRF's delete machinery.
        """
        dependent_wfs = dependent_workflow_ids(instance.pk)
        if not dependent_wfs:
            return

        deployment_types = deployment_types_for(dependent_wfs)
        # The IDs are what an operator needs to find the blocking rows;
        # `nsmallest` bounds the work for a pathological fan-out rather than
        # sorting the whole set just to slice it.
        blockers = heapq.nsmallest(
            _LOGGED_WORKFLOW_LIMIT, (str(wf) for wf in dependent_wfs)
        )
        # An unresolved deployment type is worth calling out: the deployment
        # tables are org-scoped while ``ToolInstance`` is not, so an empty set
        # can mean the dependants sit outside the active org rather than that
        # the workflows are genuinely undeployed. One line either way.
        logger.warning(
            "Cannot delete exported tool %s, depended by %d workflow(s) %s: %s",
            instance.prompt_registry_id,
            len(dependent_wfs),
            sorted(deployment_types) or "(no deployment type resolved)",
            blockers,
        )
        raise RegistryToolInUseError(self._in_use_detail(deployment_types))

    @staticmethod
    def _in_use_detail(deployment_types: set) -> str:
        """Spell out which deployments block the delete, when any are known.

        A tool can be attached to a workflow that is not deployed anywhere, so
        an empty set is normal and falls back to the generic wording.
        """
        types_text = join_deployment_types(deployment_types)
        if not types_text:
            return (
                "This exported tool is still used by one or more workflows. "
                "Remove those usages before deleting it."
            )
        return (
            f"This exported tool is still used in {types_text}. "
            "Remove those usages before deleting it."
        )
