"""Backend events that put items in users' inboxes.

Callers run these after their own change is written: on commit, or later in
the same request transaction. An inbox failure is logged and never fails the
action that caused it.
"""

import logging
import uuid
from collections.abc import Iterable
from collections.abc import Set as AbstractSet
from datetime import timedelta
from functools import partial
from typing import Any

from account_v2.models import User
from django.db.models import Max, Q
from django.utils import timezone
from tenant_account_v2.shareable_resources import descriptor_for_kind, kind_for_instance

from inbox.internal_views import RETENTION_DAYS
from inbox.models import InboxItem
from inbox.service import InboxRoute, notify, push_unread

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


def _route(kind: str, resource: Any) -> InboxRoute | None:
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
    organization, or a friction-less adapter), so a share there still tells
    its recipients. None when it
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
    had_access: AbstractSet[int] | None,
) -> None:
    """Tell users newly given access, directly or through a group, once each.

    ``had_access`` is ``users_with_access(resource)`` read before the share;
    None notifies nobody.
    """
    if had_access is None:
        return
    kind = None
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
        # No default: a wrong name_field in the registry raises and is logged.
        name = getattr(resource, descriptor_for_kind(kind).name_field)
        notify(
            recipients,
            kind=InboxItem.Kind.RESOURCE_SHARED,
            title=f"{actor.email} shared the {label} {name} with you",
            route=_route(kind, resource),
            dedupe_key=f"share:{kind}:{resource.pk}:{uuid.uuid4()}",
        )
    except Exception:
        logger.exception(
            "Could not add share notifications for %s %s (kind %s)",
            type(resource).__name__,
            getattr(resource, "pk", None),
            kind,
        )


def _run_source(execution: Any) -> tuple[Any, str, str]:
    """What ran: (resource whose owners hear about it, label, name)."""
    from api_v2.models import APIDeployment
    from pipeline_v2.models import Pipeline

    if execution.pipeline_id:
        # Base managers: callers (worker internal requests, the reaper) may have
        # no organization context, or a different one.
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


# The run an execution_failed item shows is the id in its route. The lookups
# below and _run_route are the only places that know where it sits.
_SHOWN_RUN = "route__params__id"


def _run_route(execution: Any) -> InboxRoute:
    return {"key": "execution.detail", "params": {"id": str(execution.pk)}}


def _showing(items: Any, execution: Any) -> Any:
    return items.filter(**{_SHOWN_RUN: str(execution.pk)})


def _already_points_at_this_or_newer(items: Any, execution: Any, runs: Any) -> bool:
    """True when the stored item already shows this run or a later one.

    A repeated or refused status write for a run, or a late failure of an older
    run, must not mark a read item unread or point it back in time.
    """
    # Every owner's row, not one: a former owner's row can lag behind.
    shown = set(items.values_list(_SHOWN_RUN, flat=True))
    newest = runs.filter(pk__in=shown).aggregate(newest=Max("created_at"))["newest"]
    return newest is not None and newest >= execution.created_at


def _failed_before(execution: Any, runs: Any, before: Any) -> Any:
    """The newest failed run of ``execution``'s source started before ``before``.

    Runs older than the inbox retention are left out, as their items would
    already have been purged. Not locked: a candidate for ``_previous_failure``.
    """
    from workflow_manager.workflow_v2.enums import ExecutionStatus

    if execution.pipeline_id:
        source = Q(pipeline_id=execution.pipeline_id)
    else:
        source = Q(workflow_id=execution.workflow_id, pipeline_id__isnull=True)
    # The is_failure_run rule, for terminal runs only.
    failed = Q(
        status__in=[ExecutionStatus.ERROR.value, ExecutionStatus.STOPPED.value]
    ) | Q(status=ExecutionStatus.COMPLETED.value, failed_files__gt=0)
    return (
        runs.filter(
            source,
            failed,
            created_at__lt=before,
            created_at__gte=timezone.now() - timedelta(days=RETENTION_DAYS),
        )
        .order_by("-created_at")
        .first()
    )


def _previous_failure(execution: Any, runs: Any) -> Any:
    """The newest run before ``execution`` that is still failed, row-locked.

    The lock makes a clean correction of the returned run wait until the
    caller commits; that correction then finds the item showing its run and
    hands it back again. A candidate corrected before the lock is skipped.
    """
    from notification_v2.helper import is_failure_run

    before = execution.created_at
    while candidate := _failed_before(execution, runs, before):
        locked = runs.select_for_update(of=("self",)).filter(pk=candidate.pk).first()
        if locked and is_failure_run(locked.status, locked.failed_files):
            return locked
        before = candidate.created_at
    return None


def _failure_content(execution: Any, label: str, name: str) -> dict[str, Any]:
    """Title, body and route of a failed run's item."""
    return {
        "title": _failure_title(execution, label, name)[:255],
        "body": execution.error_message or "",
        "route": _run_route(execution),
    }


def _lock_item(dedupe_key: str) -> None:
    """Transaction-scoped Postgres advisory lock on one item key."""
    from django.db import connection

    with connection.cursor() as cursor:
        # The two-key form keeps these locks apart from single-key users.
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext('inbox'), hashtext(%s))",
            [dedupe_key],
        )


def notify_on_terminal_status(execution_id: Any, status: Any) -> None:
    """Run ``notify_execution_failed`` on commit when ``status`` ends the run.

    Callers write the run's file counts in the same transaction as the status,
    or the callback sees stale counts.
    """
    from django.db import transaction
    from workflow_manager.workflow_v2.enums import ExecutionStatus

    try:
        status = ExecutionStatus(status)
    except ValueError:
        return
    if status in (
        ExecutionStatus.COMPLETED,
        ExecutionStatus.ERROR,
        ExecutionStatus.STOPPED,
    ):
        transaction.on_commit(partial(notify_execution_failed, execution_id))


def notify_execution_failed(execution_id: Any) -> None:
    """Tell the owners of what ran when a run fails.

    Each owner keeps one item per pipeline, API deployment or workflow: a new
    failure refreshes it to the latest run and marks it unread again, so a
    resource that keeps failing does not flood the inbox. Registered through
    ``notify_on_terminal_status`` by ``WorkflowExecution.update_execution`` and
    the internal batch status endpoint.

    ERROR can later be corrected to a clean COMPLETED. A clean finish of the
    run an item shows hands the item back to the newest earlier failure of the
    same source, or withdraws it when there is none.
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
        # No execution row lock needed: a failure callback for this run either
        # stored its item before this run's status write could take the row
        # lock, or re-read the clean run and stored nothing. Most clean runs
        # have no item, so they skip the item lock too; when there is one, the
        # item lock keeps this change from interleaving with another run's
        # refresh.
        mine = _showing(items, execution)
        if mine.exists():
            with transaction.atomic():
                _lock_item(dedupe_key)
                _hand_back_or_withdraw(mine, execution, runs, organization)
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
        owners = _members_of(organization, resource.owners())
        if not owners:
            logger.warning(
                "Run %s: %s %s has no owners in its organization; no inbox item",
                execution.pk,
                label,
                name,
            )
            return
        notify(
            owners,
            kind=InboxItem.Kind.EXECUTION_FAILED,
            **_failure_content(execution, label, name),
            dedupe_key=dedupe_key,
            organization=organization,
            refresh=True,
        )


def _members_of(organization: Any, users: Iterable[User]) -> list[User]:
    """``users`` who are still members of ``organization``."""
    from tenant_account_v2.models import OrganizationMember

    users = list(users)
    # Base manager: the organization context may be absent or another one.
    members = set(
        OrganizationMember._base_manager.filter(
            organization=organization, user__in=users
        ).values_list("user_id", flat=True)
    )
    return [user for user in users if user.pk in members]


def _hand_back_or_withdraw(
    mine: Any, execution: Any, runs: Any, organization: Any
) -> None:
    """Point ``mine`` at the previous failure, or delete it; read state is kept."""
    user_ids = list(mine.values_list("user_id", flat=True))
    if not user_ids:
        return
    previous = _previous_failure(execution, runs)
    if previous:
        _, label, name = _run_source(previous)
        # A base-manager queryset, so modified_at is set here.
        mine.update(**_failure_content(previous, label, name), modified_at=timezone.now())
    else:
        mine.delete()
    push_unread(organization, user_ids)
