"""OSS result types.

Each provider starts from the same ``Model.objects.for_user(user)`` its list
view uses, plus that list's own fixed filters, so search never returns a row
the caller could not open from the list.
"""

from __future__ import annotations

from typing import Any

from adapter_processor_v2.models import AdapterInstance
from api_v2.models import APIDeployment
from connector_v2.models import ConnectorInstance
from django.contrib.contenttypes.models import ContentType
from django.db.models import CharField, F, Model, OuterRef, QuerySet, Subquery
from django.db.models.functions import Cast
from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from tenant_account_v2.models import ResourceMembership
from workflow_manager.workflow_v2.models.workflow import Workflow

from global_search.constants import OSSSearchType
from global_search.providers import ModelSearchProvider

OWNER_EMAIL = "_search_owner_email"
PARENT_NAME = "_search_parent_name"

# D12 retires the No Op adapters in v1; their ids share this prefix.
NO_OP_ADAPTER_PREFIX = "noOp"


def owner_email_subquery(model: type[Model]) -> Subquery:
    """Earliest live, non-service-account OWNER's e-mail, as one correlated
    subquery. Same rule as ``HasMembersMixin.owner_email`` without the
    per-row prefetch.
    """
    return Subquery(
        ResourceMembership.objects.filter(
            content_type=ContentType.objects.get_for_model(model),
            object_id=Cast(OuterRef("pk"), output_field=CharField()),
            role=ResourceRole.OWNER,
            user__is_service_account=False,
        )
        .order_by("created_at", "pk")
        .values("user__email")[:1]
    )


def _provider(registry_id: str) -> str:
    """Provider slug from an adapter/connector registry id (``openai|<uuid>``)."""
    return registry_id.split("|", 1)[0] if registry_id else ""


class OwnedModelProvider(ModelSearchProvider):
    """Context line is the owner's e-mail."""

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.annotate(**{OWNER_EMAIL: owner_email_subquery(queryset.model)})

    def context(self, obj: Model) -> str | None:
        return getattr(obj, OWNER_EMAIL)


class WorkflowChildProvider(ModelSearchProvider):
    """Context line is the parent workflow's name."""

    def annotate(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        return queryset.annotate(**{PARENT_NAME: F("workflow__workflow_name")})

    def context(self, obj: Model) -> str | None:
        return getattr(obj, PARENT_NAME)


class PromptStudioProjectProvider(OwnedModelProvider):
    type_key = OSSSearchType.PROMPT_STUDIO_PROJECT
    label = "Prompt Studio projects"
    order = 10
    name_fields = ("tool_name",)
    description_field = "description"

    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        return CustomTool.objects.for_user(user)


class WorkflowProvider(OwnedModelProvider):
    type_key = OSSSearchType.WORKFLOW
    label = "Workflows"
    order = 30
    name_fields = ("workflow_name",)
    description_field = "description"

    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        return Workflow.objects.for_user(user)


class APIDeploymentProvider(WorkflowChildProvider):
    type_key = OSSSearchType.API_DEPLOYMENT
    label = "API deployments"
    order = 40
    name_fields = ("display_name", "api_name")
    description_field = "description"

    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        return APIDeployment.objects.for_user(user)


class _PipelineProvider(WorkflowChildProvider):
    pipeline_type: str
    name_fields = ("pipeline_name",)

    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        return Pipeline.objects.for_user(user).filter(pipeline_type=self.pipeline_type)


class ETLPipelineProvider(_PipelineProvider):
    type_key = OSSSearchType.ETL_PIPELINE
    label = "ETL pipelines"
    order = 50
    pipeline_type = Pipeline.PipelineType.ETL


class TaskPipelineProvider(_PipelineProvider):
    type_key = OSSSearchType.TASK_PIPELINE
    label = "Task pipelines"
    order = 60
    pipeline_type = Pipeline.PipelineType.TASK


class AdapterProvider(ModelSearchProvider):
    type_key = OSSSearchType.ADAPTER
    label = "Adapters"
    order = 80
    name_fields = ("adapter_name",)
    description_field = "description"

    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        return AdapterInstance.objects.for_user(user).exclude(
            adapter_id__startswith=NO_OP_ADAPTER_PREFIX
        )

    def context(self, obj: Model) -> str | None:
        return " · ".join(p for p in (obj.adapter_type, _provider(obj.adapter_id)) if p)

    def route_params(self, obj: Model) -> dict[str, str]:
        return {"id": str(obj.pk), "adapter_type": obj.adapter_type}


class ConnectorProvider(ModelSearchProvider):
    type_key = OSSSearchType.CONNECTOR
    label = "Connectors"
    order = 90
    name_fields = ("connector_name",)

    def visible_queryset(self, user: Any) -> QuerySet[Any]:
        return ConnectorInstance.objects.for_user(user)

    def context(self, obj: Model) -> str | None:
        return _provider(obj.connector_id) or None


OSS_PROVIDERS = (
    PromptStudioProjectProvider,
    WorkflowProvider,
    APIDeploymentProvider,
    ETLPipelineProvider,
    TaskPipelineProvider,
    AdapterProvider,
    ConnectorProvider,
)
