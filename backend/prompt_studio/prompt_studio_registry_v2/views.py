import logging
from typing import Any

from api_v2.models import APIDeployment
from django.db.models import QuerySet
from pipeline_v2.models import Pipeline
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from tool_instance_v2.models import ToolInstance
from utils.filtering import FilterHelper
from workflow_manager.endpoint_v2.models import WorkflowEndpoint

from prompt_studio.permission import IsRegistryToolOwner
from prompt_studio.prompt_studio_core_v2.constants import DeploymentType
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

    def _get_deployment_types(self, workflow_ids: set) -> set:
        """Name the deployment kinds that reach ``workflow_ids``.

        Mirrors ``PromptStudioCoreView._get_deployment_types``
        (``prompt_studio_core_v2/views.py:249``) so the refusal can say *where*
        the tool is still used rather than only that it is.
        """
        deployment_types: set = set()

        # Inactive deployments are included: they still reference the tool and
        # would break on re-activation.
        if APIDeployment.objects.filter(workflow_id__in=workflow_ids).exists():
            deployment_types.add(DeploymentType.API_DEPLOYMENT)

        pipeline_type_mapping = {
            Pipeline.PipelineType.ETL: DeploymentType.ETL_PIPELINE,
            Pipeline.PipelineType.TASK: DeploymentType.TASK_PIPELINE,
        }
        pipeline_types = (
            Pipeline.objects.filter(workflow_id__in=workflow_ids)
            .values_list("pipeline_type", flat=True)
            .distinct()
        )
        for pipeline_type in pipeline_types:
            if pipeline_type in pipeline_type_mapping:
                deployment_types.add(pipeline_type_mapping[pipeline_type])

        if WorkflowEndpoint.objects.filter(
            workflow_id__in=workflow_ids,
            connection_type=WorkflowEndpoint.ConnectionType.MANUALREVIEW,
        ).exists():
            deployment_types.add(DeploymentType.HUMAN_QUALITY_REVIEW)

        return deployment_types

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
        dependent_wfs = set(
            ToolInstance.objects.filter(tool_id=instance.pk)
            .values_list("workflow_id", flat=True)
            .distinct()
        )
        if not dependent_wfs:
            return
        logger.info(
            f"Cannot delete exported tool {instance.prompt_registry_id}, "
            f"depended by {len(dependent_wfs)} workflow(s)"
        )
        raise RegistryToolInUseError(
            self._in_use_detail(self._get_deployment_types(dependent_wfs))
        )

    @staticmethod
    def _in_use_detail(deployment_types: set) -> str:
        """Spell out which deployments block the delete, when any are known.

        A tool can be attached to a workflow that is not deployed anywhere, so
        an empty set is normal and falls back to the generic wording.
        """
        if not deployment_types:
            return (
                "This exported tool is still used by one or more workflows. "
                "Remove those usages before deleting it."
            )
        types_list = sorted(deployment_types)
        if len(types_list) == 1:
            types_text = types_list[0]
        elif len(types_list) == 2:
            types_text = f"{types_list[0]} or {types_list[1]}"
        else:
            types_text = ", ".join(types_list[:-1]) + f", or {types_list[-1]}"
        return (
            f"This exported tool is still used in {types_text}. "
            "Remove those usages before deleting it."
        )
