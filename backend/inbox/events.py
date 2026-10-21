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
    try:
        by_group = _group_recipients_batch(UserContext.get_organization(), groups, set())
    except Exception:
        # The users shared with directly are still told.
        logger.exception(
            "Could not read the members of groups %s", [g.pk for g in groups]
        )
        return set()
    return {user for members in by_group.values() for user in members}


def users_with_access(resource: Any) -> set[int] | None:
    """Ids of users who already reach ``resource``; read before a share changes it.

    Empty when access does not depend on shares (shared with the whole
    organization), so a share there still tells its recipients. None when it
    could not be read: the share then notifies nobody rather than everyone.
    """
    from tenant_account_v2.sharing_helpers import retained_user_ids

    try:
        return retained_user_ids(resource) or set()
    except Exception:
        logger.exception(
            "Could not read who can access %s", getattr(resource, "pk", None)
        )
        return None


def notify_resource_shared(
    *,
    resource: Any,
    users: Iterable[User],
    groups: Iterable[Any],
    actor: User,
    had_access: set[int] | None = frozenset(),
) -> None:
    """Tell users newly given access, directly or through a group, once each."""
    if had_access is None:
        return
    try:
        kind = kind_for_instance(resource)
        if kind not in _SHARED_KINDS:
            return
        recipients = {
            user
            for user in set(users) | _group_members(groups)
            if user != actor and user.pk not in had_access
        }
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


def _run_source(execution: Any) -> tuple[Any, str, str]:
    """What ran: (resource whose owners hear about it, label, name)."""
    from api_v2.models import APIDeployment
    from pipeline_v2.models import Pipeline

    if execution.pipeline_id:
        # Base managers: this runs in worker requests with no organization context.
        pipeline = Pipeline._base_manager.filter(pk=execution.pipeline_id).first()
        if pipeline:
            return pipeline, "pipeline", pipeline.pipeline_name
        api = APIDeployment._base_manager.filter(pk=execution.pipeline_id).first()
        if api:
            return api, "API deployment", api.api_name
        logger.warning(
            "Run %s names a pipeline or API deployment %s that no longer exists; "
            "telling the workflow's owners",
            execution.pk,
            execution.pipeline_id,
        )
    workflow = execution.workflow
    return workflow, "workflow", workflow.workflow_name


def _failure_title(execution: Any, label: str, name: str) -> str:
    from workflow_manager.workflow_v2.enums import ExecutionStatus

    if execution.status == ExecutionStatus.ERROR.value:
        return f"A run of the {label} {name} failed"
    if execution.status == ExecutionStatus.STOPPED.value:
        return f"A run of the {label} {name} was stopped"
    return (
        f"A run of the {label} {name} finished with {execution.failed_files} failed files"
    )


def _already_points_at_this_or_newer(items: Any, execution: Any, runs: Any) -> bool:
    """True when the stored item already shows this run or a later one.

    A repeated or refused status write for a run, or a late failure of an older
    run, must not mark a read item unread or point it back in time.
    """
    shown = items.values_list("route__params__id", flat=True).first()
    if shown is None:
        return False
    if shown == str(execution.pk):
        return True
    shown_run = runs.filter(pk=shown).values_list("created_at", flat=True).first()
    return shown_run is not None and shown_run > execution.created_at


def _lock_item(dedupe_key: str) -> None:
    """Transaction-scoped Postgres advisory lock on one item key."""
    from django.db import connection

    with connection.cursor() as cursor:
        # The two-key form keeps these locks apart from single-key users.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext('inbox'), hashtext(%s))",
            [dedupe_key],
        )


def notify_execution_failed(execution_id: Any) -> None:
    """Tell the owners of what ran when a run fails.

    Each owner keeps one item per pipeline, API deployment or workflow: a new
    failure refreshes it to the latest run and marks it unread again, so a
    resource that keeps failing does not flood the inbox. Registered by
    ``WorkflowExecution.update_execution`` for COMPLETED, ERROR and STOPPED.
    ERROR can later be corrected to a clean COMPLETED, so a clean finish
    withdraws the item while it still points at that run.
    """
    try:
        _notify_execution_failed(execution_id)
    except Exception:
        logger.exception("Could not add failed-run notifications for %s", execution_id)


def _notify_execution_failed(execution_id: Any) -> None:
    from django.db import transaction
    from notification_v2.helper import is_failure_run
    from workflow_manager.workflow_v2.models import WorkflowExecution

    runs = WorkflowExecution.objects.select_related("workflow__organization")
    execution = runs.filter(pk=execution_id).first()
    if not execution:
        return
    organization = execution.workflow.organization
    if organization is None:
        logger.warning("Run %s has no organization; no inbox item", execution.pk)
        return
    dedupe_key = f"run_failed:{execution.pipeline_id or execution.workflow_id}"
    items = InboxItem._base_manager.filter(
        organization=organization, dedupe_key=dedupe_key
    )
    if not is_failure_run(execution.status, execution.failed_files):
        # No row lock needed: a failure being recorded holds this run's row
        # lock, and this run's own status write waited for it, so the item is
        # already stored. The item lock keeps the delete off a concurrent refresh.
        with transaction.atomic():
            _lock_item(dedupe_key)
            items.filter(route__params__id=str(execution.pk)).delete()
        return
    with transaction.atomic():
        # The item lock serialises runs of one resource, so the newest-run check
        # and the refresh below act as one step.
        _lock_item(dedupe_key)
        # The row lock holds off a concurrent status write until this decision
        # is stored, so a clean correction always runs after the item it
        # withdraws.
        execution = runs.select_for_update(of=("self",)).filter(pk=execution_id).first()
        if not execution or not is_failure_run(execution.status, execution.failed_files):
            return
        if _already_points_at_this_or_newer(items, execution, runs):
            return
        resource, label, name = _run_source(execution)
        notify(
            resource.owners(),
            kind=InboxItem.Kind.EXECUTION_FAILED,
            title=_failure_title(execution, label, name),
            body=execution.error_message or "",
            route={"key": "execution.detail", "params": {"id": str(execution.pk)}},
            dedupe_key=dedupe_key,
            organization=organization,
            refresh=True,
            # Keeps the count query off the status-write path; the new count
            # shows on the next list call.
            push=False,
        )
