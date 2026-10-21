"""Backend events that put items in users' inboxes.

Callers run these after their own change has committed. An inbox failure is
logged and never fails the action that caused it.
"""

import logging
import uuid
from collections.abc import Iterable
from typing import Any

from account_v2.models import User
from tenant_account_v2.shareable_resources import descriptor_for_kind, kind_for_instance

from inbox.models import InboxItem
from inbox.service import notify

logger = logging.getLogger(__name__)

# Share kind -> (label in the title, global search route key).
_SHARED_KINDS: dict[str, tuple[str, str | None]] = {
    "workflow": ("workflow", "workflow.detail"),
    "pipeline": ("pipeline", None),  # key depends on the pipeline type
    "api_deployment": ("API deployment", "api_deployment.detail"),
    "connector_instance": ("connector", "connector.detail"),
    # Shared users are viewers, so the read-only adapter page.
    "adapter_instance": ("adapter", "adapter.info"),
    "custom_tool": ("Prompt Studio project", "prompt_studio_project.detail"),
    "agentic_project": ("Agentic Studio project", "agentic_project.detail"),
    "lookup": ("look-up", None),
}
_PIPELINE_ROUTE_KEYS = {"ETL": "etl_pipeline.detail", "TASK": "task_pipeline.detail"}


def _route(kind: str, resource: Any) -> dict[str, Any] | None:
    key = _SHARED_KINDS[kind][1]
    if kind == "pipeline":
        key = _PIPELINE_ROUTE_KEYS.get(getattr(resource, "pipeline_type", ""))
    if not key:
        return None
    params = {"id": str(resource.pk)}
    if kind == "adapter_instance":
        params["adapter_type"] = resource.adapter_type
    return {"key": key, "params": params}


def _group_members(groups: Iterable[Any]) -> set[User]:
    # Live org members only, as the group share e-mail resolves them.
    from tenant_account_v2.group_notification_service import _group_recipients_batch
    from utils.user_context import UserContext

    groups = list(groups)
    if not groups:
        return set()
    by_group = _group_recipients_batch(UserContext.get_organization(), groups, set())
    return {user for members in by_group.values() for user in members}


def notify_resource_shared(
    *, resource: Any, users: Iterable[User], groups: Iterable[Any], actor: User
) -> None:
    """Tell users newly given access, directly or through a group, once each."""
    try:
        kind = kind_for_instance(resource)
        if kind not in _SHARED_KINDS:
            return
        recipients = (set(users) | _group_members(groups)) - {actor}
        if not recipients:
            return
        label = _SHARED_KINDS[kind][0]
        name = getattr(resource, descriptor_for_kind(kind).name_field, "")
        notify(
            recipients,
            kind=InboxItem.Kind.RESOURCE_SHARED,
            title=f"{actor.email} shared the {label} {name} with you",
            route=_route(kind, resource),
            dedupe_key=f"share:{kind}:{resource.pk}:{uuid.uuid4()}",
        )
    except Exception:
        logger.exception(
            "Could not add share notifications for %s", getattr(resource, "pk", None)
        )


def _run_source(execution: Any) -> tuple[Any, str, str, str | None]:
    """What ran: (resource whose owners hear about it, label, name, route key)."""
    from api_v2.models import APIDeployment
    from pipeline_v2.models import Pipeline

    if execution.pipeline_id:
        # Base managers: this runs in worker requests with no organization context.
        pipeline = Pipeline._base_manager.filter(pk=execution.pipeline_id).first()
        if pipeline:
            key = _PIPELINE_ROUTE_KEYS.get(pipeline.pipeline_type)
            return pipeline, "pipeline", pipeline.pipeline_name, key
        api = APIDeployment._base_manager.filter(pk=execution.pipeline_id).first()
        if api:
            return api, "API deployment", api.api_name, "api_deployment.detail"
    workflow = execution.workflow
    return workflow, "workflow", workflow.workflow_name, "workflow.detail"


def _failure_title(execution: Any, label: str, name: str) -> str:
    from workflow_manager.workflow_v2.enums import ExecutionStatus

    if execution.status == ExecutionStatus.ERROR.value:
        return f"A run of the {label} {name} failed"
    if execution.status == ExecutionStatus.STOPPED.value:
        return f"A run of the {label} {name} was stopped"
    return (
        f"A run of the {label} {name} finished with {execution.failed_files} failed files"
    )


def notify_execution_failed(execution_id: Any) -> None:
    """Tell the owners of what ran, once per execution, when a run fails."""
    from notification_v2.helper import is_failure_run
    from workflow_manager.workflow_v2.models import WorkflowExecution

    try:
        execution = (
            WorkflowExecution.objects.select_related("workflow__organization")
            .filter(pk=execution_id)
            .first()
        )
        if not execution or not is_failure_run(execution.status, execution.failed_files):
            # ponytail: an ERROR later corrected to a clean COMPLETED keeps its item;
            # delete it here if premature errors turn out to be common.
            return
        resource, label, name, key = _run_source(execution)
        notify(
            resource.owners(),
            kind=InboxItem.Kind.EXECUTION_FAILED,
            title=_failure_title(execution, label, name),
            body=execution.error_message or "",
            route={"key": key, "params": {"id": str(resource.pk)}} if key else None,
            dedupe_key=f"execution_failed:{execution.pk}",
            organization=execution.workflow.organization,
        )
    except Exception:
        logger.exception("Could not add failed-run notifications for %s", execution_id)
