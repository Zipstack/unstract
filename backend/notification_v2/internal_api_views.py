"""Internal API views for notification data access by workers.

These endpoints provide notification configuration data to workers
without exposing full Django models or requiring Django dependencies.

Security Note:
- CSRF protection is disabled for internal service-to-service communication
- Authentication is handled by InternalAPIAuthMiddleware using Bearer tokens
- These endpoints are not accessible from browsers and don't use session cookies
"""

import json
import logging
from datetime import timedelta
from typing import Any, cast

from api_v2.models import APIDeployment
from django.conf import settings
from django.db import transaction
from django.db.models import Min, QuerySet
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from pipeline_v2.models import Pipeline
from utils.organization_utils import filter_queryset_by_organization
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from backend.celery_service import app as celery_app
from notification_v2.clubbed_renderer import MAX_BATCH_SIZE, render_clubbed_message
from notification_v2.enums import BufferStatus
from notification_v2.helper import (
    build_webhook_headers,
    enqueue,
    is_failure_run,
    webhook_url_hash,
)
from notification_v2.models import Notification, NotificationBuffer

logger = logging.getLogger(__name__)

# Constants for error messages
INTERNAL_SERVER_ERROR_MSG = "Internal server error"


def _load_execution(execution_id: str | None) -> WorkflowExecution | None:
    """Best-effort lookup; returns None on missing id or unknown row."""
    if not execution_id:
        return None
    try:
        return cast(WorkflowExecution, WorkflowExecution.objects.get(id=execution_id))
    except WorkflowExecution.DoesNotExist:
        logger.warning("WorkflowExecution %s not found", execution_id)
        return None


def _apply_failure_filter(
    notifications_qs: QuerySet[Notification],
    execution: WorkflowExecution | None,
) -> QuerySet[Notification]:
    """Drop notify_on_failures=True rows on success runs.

    Uses the shared rule in notification_v2.helper.is_failure_run (status ∈
    {ERROR, STOPPED} OR any file errored), the same rule applied by
    backend/api_v2/notification.py. The pipeline backend path
    (backend/pipeline_v2/notification.py) ORs an additional last_run_status
    backstop on top for the case where no WorkflowExecution exists; this
    callback path always has the execution, so it does not need that term.

    No execution → no filter, preserving legacy "return every active row"
    behavior for callers that don't pass execution_id.
    """
    if execution is None:
        return notifications_qs
    if not is_failure_run(execution.status, execution.failed_files):
        notifications_qs = notifications_qs.filter(notify_on_failures=False)
    return notifications_qs


def _execution_counts(execution: WorkflowExecution | None) -> dict[str, int]:
    """File counts surfaced into webhook payloads. Empty dict on no execution."""
    if execution is None:
        return {}
    return {
        "total_files": execution.total_files or 0,
        "successful_files": execution.successful_files or 0,
        "failed_files": execution.failed_files or 0,
    }


def _serialize_notification(n: Notification) -> dict[str, Any]:
    return {
        "id": str(n.id),
        "notification_type": n.notification_type,
        "platform": n.platform,
        "url": n.url,
        "authorization_type": n.authorization_type,
        "authorization_key": n.authorization_key,
        "authorization_header": n.authorization_header,
        "max_retries": n.max_retries,
        "is_active": n.is_active,
        "notify_on_failures": n.notify_on_failures,
    }


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_pipeline_notifications(request: HttpRequest, pipeline_id: str) -> JsonResponse:
    """Get active notifications for a pipeline or API deployment.

    Used by callback worker to fetch notification configuration.
    """
    try:
        # Try to find the pipeline ID in Pipeline model first
        pipeline_queryset = Pipeline.objects.filter(id=pipeline_id)
        pipeline_queryset = filter_queryset_by_organization(
            pipeline_queryset, request, "organization"
        )

        execution = _load_execution(request.GET.get("execution_id"))
        counts = _execution_counts(execution)

        if pipeline_queryset.exists():
            pipeline = pipeline_queryset.first()
            notifications = Notification.objects.filter(pipeline=pipeline, is_active=True)
            notifications = _apply_failure_filter(notifications, execution)
            serialized = [_serialize_notification(n) for n in notifications]
            return JsonResponse(
                {
                    "status": "success",
                    "pipeline_id": str(pipeline.id),
                    "pipeline_name": pipeline.pipeline_name,
                    "pipeline_type": pipeline.pipeline_type,
                    "notifications": serialized,
                    "execution_counts": counts,
                }
            )

        # If not found in Pipeline, try APIDeployment model
        api_queryset = APIDeployment.objects.filter(id=pipeline_id)
        api_queryset = filter_queryset_by_organization(
            api_queryset, request, "organization"
        )
        if api_queryset.exists():
            api = api_queryset.first()
            notifications = Notification.objects.filter(api=api, is_active=True)
            notifications = _apply_failure_filter(notifications, execution)
            serialized = [_serialize_notification(n) for n in notifications]
            return JsonResponse(
                {
                    "status": "success",
                    "pipeline_id": str(api.id),
                    "pipeline_name": api.api_name,
                    "pipeline_type": "API",
                    "notifications": serialized,
                    "execution_counts": counts,
                }
            )

        return JsonResponse(
            {
                "status": "error",
                "message": "Pipeline or API deployment not found",
            },
            status=404,
        )
    except Exception as e:
        logger.error(f"Error getting pipeline notifications for {pipeline_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_api_notifications(request: HttpRequest, api_id: str) -> JsonResponse:
    """Get active notifications for an API deployment.

    Used by callback worker to fetch notification configuration.
    """
    try:
        # Get API deployment with organization filtering
        api_queryset = APIDeployment.objects.filter(id=api_id)
        api_queryset = filter_queryset_by_organization(
            api_queryset, request, "organization"
        )
        api = get_object_or_404(api_queryset)

        execution = _load_execution(request.GET.get("execution_id"))
        notifications = Notification.objects.filter(api=api, is_active=True)
        notifications = _apply_failure_filter(notifications, execution)

        return JsonResponse(
            {
                "status": "success",
                "api_id": str(api.id),
                "api_name": api.api_name,
                "display_name": api.display_name,
                "notifications": [_serialize_notification(n) for n in notifications],
                "execution_counts": _execution_counts(execution),
            }
        )

    except APIDeployment.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "API deployment not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting API notifications for {api_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_pipeline_data(request: HttpRequest, pipeline_id: str) -> JsonResponse:
    """Get basic pipeline data for notification purposes.

    Used by callback worker to determine pipeline type and name.
    """
    try:
        # Get pipeline with organization filtering
        pipeline_queryset = Pipeline.objects.filter(id=pipeline_id)
        pipeline_queryset = filter_queryset_by_organization(
            pipeline_queryset, request, "organization"
        )
        pipeline = get_object_or_404(pipeline_queryset)

        return JsonResponse(
            {
                "status": "success",
                "pipeline_id": str(pipeline.id),
                "pipeline_name": pipeline.pipeline_name,
                "pipeline_type": pipeline.pipeline_type,
                "last_run_status": pipeline.last_run_status,
            }
        )

    except Pipeline.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Pipeline not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting pipeline data for {pipeline_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["GET"])
def get_api_data(request: HttpRequest, api_id: str) -> JsonResponse:
    """Get basic API deployment data for notification purposes.

    Used by callback worker to determine API name and details.
    """
    try:
        # Get API deployment with organization filtering
        api_queryset = APIDeployment.objects.filter(id=api_id)
        api_queryset = filter_queryset_by_organization(
            api_queryset, request, "organization"
        )
        api = get_object_or_404(api_queryset)

        return JsonResponse(
            {
                "status": "success",
                "api_id": str(api.id),
                "api_name": api.api_name,
                "display_name": api.display_name,
                "is_active": api.is_active,
            }
        )

    except APIDeployment.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "API deployment not found"}, status=404
        )
    except Exception as e:
        logger.error(f"Error getting API data for {api_id}: {e}")
        return JsonResponse(
            {"status": "error", "message": INTERNAL_SERVER_ERROR_MSG}, status=500
        )


# `execution_id` is required except for INPROGRESS, which fires from the
# scheduler before the WorkflowExecution exists. INPROGRESS rows therefore
# store execution_id=null — receivers cannot correlate with execution logs
# until the producer ordering is changed.
_ENQUEUE_REQUIRED_FIELDS = (
    "notification_id",
    "pipeline_id",
    "pipeline_name",
    "status",
    "platform",
    "execution_id",
)


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["POST"])
def enqueue_notification_buffer(request: HttpRequest) -> JsonResponse:
    """Buffer one execution event from a callback worker.

    Worker code is model-free: it forwards a notification_id + structured
    payload here and lets the backend write the NotificationBuffer row.
    Rejects rows whose source notification is not BATCHED so a worker
    routing bug cannot silently divert non-BATCHED traffic into the buffer.
    """
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON body"}, status=400
        )

    missing_fields = [f for f in _ENQUEUE_REQUIRED_FIELDS if not body.get(f)]
    # INPROGRESS is the one status legitimately allowed to omit execution_id
    # (see comment on _ENQUEUE_REQUIRED_FIELDS).
    if (
        body.get("status") == Pipeline.PipelineStatus.INPROGRESS
        and "execution_id" in missing_fields
    ):
        missing_fields.remove("execution_id")
    if missing_fields:
        return JsonResponse(
            {
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing_fields)}",
            },
            status=400,
        )

    try:
        notification = Notification.objects.get(id=body["notification_id"])
    except Notification.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Notification not found"}, status=404
        )

    # INPROGRESS fires from the scheduler before a WorkflowExecution exists,
    # so the GET-side `_apply_failure_filter` cannot run (no execution → no
    # filter applied) and returns notify_on_failures=True rows too. Drop the
    # event here so failure-only subscribers never receive a run-start.
    if (
        notification.notify_on_failures
        and body.get("status") == Pipeline.PipelineStatus.INPROGRESS
    ):
        return JsonResponse({"status": "ok", "buffer_row_id": None})

    # type / timestamp / additional_data stay optional during rollout — older
    # worker builds that don't forward them still produce a usable row; the
    # single-line clubbed renderer simply omits the missing fields.
    payload = {
        "type": body.get("type", ""),
        "execution_id": body.get("execution_id"),
        "pipeline_id": body["pipeline_id"],
        "pipeline_name": body["pipeline_name"],
        "status": body["status"],
        "error_message": body.get("error_message"),
        "platform": body["platform"],
        "timestamp": body.get("timestamp"),
        "additional_data": body.get("additional_data") or {},
    }
    try:
        buffer_row = enqueue(notification, payload)
    except ValueError as e:
        return JsonResponse({"status": "error", "message": str(e)}, status=400)

    return JsonResponse(
        {"status": "success", "buffer_row_id": str(buffer_row.id)}, status=201
    )


def _gc_terminal_rows() -> int:
    """Delete buffer rows past the retention window.

    Two sweeps:
    - Terminal rows (DISPATCHED / DEAD_LETTER) older than the retention
      window: hygiene for completed work.
    - PENDING rows whose source notification has been deactivated and
      whose ``flush_after`` has aged past the same window: ``_dispatch_group``
      filters ``notification__is_active=True``, so without this sweep
      these rows are unreachable from both dispatch and GC and would
      accumulate forever in the partial PENDING index.

    PENDING rows attached to active notifications are intentionally
    untouched regardless of age — they represent live work the flush
    job still owns.
    """
    cutoff = timezone.now() - timedelta(days=settings.NOTIFICATION_BUFFER_RETENTION_DAYS)
    terminal_deleted, _ = NotificationBuffer.objects.filter(
        status__in=[BufferStatus.DISPATCHED.value, BufferStatus.DEAD_LETTER.value],
        created_at__lt=cutoff,
    ).delete()
    inactive_deleted, _ = NotificationBuffer.objects.filter(
        status=BufferStatus.PENDING.value,
        notification__is_active=False,
        flush_after__lt=cutoff,
    ).delete()
    return int(terminal_deleted) + int(inactive_deleted)


def _reclaim_stale_sending() -> int:
    """Return rows stuck in SENDING past the dispatch lease to PENDING.

    Covers the crash window where a flush committed the SENDING claim but no
    terminal callback ever ran (e.g. the backend died before the on_commit
    publish, or the worker vanished). The lease must exceed the worst-case retry
    duration so genuinely in-flight dispatches are never reclaimed mid-flight.
    """
    cutoff = timezone.now() - timedelta(
        seconds=settings.NOTIFICATION_DISPATCH_LEASE_SECONDS
    )
    reclaimed = NotificationBuffer.objects.filter(
        status=BufferStatus.SENDING.value,
        dispatched_at__lt=cutoff,
    ).update(status=BufferStatus.PENDING.value, dispatched_at=None)
    if reclaimed:
        logger.warning("metric=notification_buffer_reclaimed_total rows=%d", reclaimed)
    return int(reclaimed)


def _send_clubbed(
    *,
    url: str,
    body: Any,
    headers: dict[str, str],
    platform: str,
    max_retries: int,
    buffer_ids: list[str],
    org_id: Any,
) -> None:
    """Send the clubbed Celery task after the DB transition has committed.

    Runs as a ``transaction.on_commit`` callback so a rolled-back UPDATE can
    never leave a broker-queued message orphaned (the prior order — send
    then update — risked duplicate delivery if the UPDATE failed). On broker
    failure we revert rows back to PENDING in a separate transaction so the
    next flush tick retries cleanly.
    """
    try:
        celery_app.send_task(
            "send_webhook_notification",
            args=[url, body, headers, settings.NOTIFICATION_TIMEOUT],
            kwargs={
                "max_retries": max_retries,
                "retry_delay": 10,
                "platform": platform,
                # Re-raise on retry exhaustion so the task ends in FAILURE and the
                # link_error below runs — otherwise the worker returns None (SUCCESS)
                # and the buffer rows would never reach DEAD_LETTER.
                "raise_on_final_failure": True,
            },
            queue="notifications",
            link=celery_app.signature(
                "notification_v2.mark_buffer_dispatched",
                kwargs={"buffer_row_ids": buffer_ids},
            ),
            link_error=celery_app.signature(
                "notification_v2.mark_buffer_dead_letter",
                kwargs={"buffer_row_ids": buffer_ids},
            ),
        )
        logger.info(
            "metric=notification_batch_dispatched_total platform=%s result=success "
            "org_id=%s webhook_url_hash=%s rows=%d",
            platform,
            org_id,
            webhook_url_hash(url),
            len(buffer_ids),
        )
    except Exception:
        logger.exception(
            "metric=notification_batch_dispatched_total platform=%s "
            "result=broker_failure org_id=%s webhook_url_hash=%s rows=%d",
            platform,
            org_id,
            webhook_url_hash(url),
            len(buffer_ids),
        )
        # Revert outside the committed transaction so a transient broker
        # outage degrades to "retried next tick" rather than "stuck DISPATCHED".
        NotificationBuffer.objects.filter(id__in=buffer_ids).update(
            status=BufferStatus.PENDING.value,
            dispatched_at=None,
        )


def _dispatch_group(
    org_id: Any,
    webhook_url: str,
    auth_sig: str,
    platform: str,
) -> tuple[int, int]:
    """Dispatch a single (org, url, auth_sig, platform) group; returns (rows, succeeded).

    Caller already filtered groups to MIN(flush_after) <= now. Locks rows
    with SKIP LOCKED so a sibling replica skips them rather than blocking.
    Re-fetches the source Notification each time for live auth (record may
    have been edited between enqueue and flush).
    """
    with transaction.atomic():
        rows = list(
            NotificationBuffer.objects.select_for_update(skip_locked=True)
            .select_related("notification")
            .filter(
                status=BufferStatus.PENDING.value,
                organization_id=org_id,
                webhook_url=webhook_url,
                auth_sig=auth_sig,
                platform=platform,
                notification__is_active=True,
            )
            .order_by("created_at")[:_PROCESS_BUFFER_CAP]
        )
        if not rows:
            # Either another replica claimed the rows (SKIP LOCKED) or they
            # transitioned out of PENDING between the GROUP BY scan and the
            # row-level lock. Either way: nothing to do here.
            return 0, 0

        # Live auth — read from the FIRST row's notification. If multiple
        # notifications collide on (url, auth_sig, platform) we have, by
        # definition, identical auth + format, so this is safe. Retry budget
        # is the MAX across rows: there's a single HTTP call per batch, so
        # the most retry-tolerant subscriber's intent wins; using the first
        # row's value would silently truncate everyone else's retry budget.
        first_notification = rows[0].notification
        payloads = [r.payload for r in rows]
        body = render_clubbed_message(payloads, platform)
        headers = build_webhook_headers(first_notification)
        buffer_ids = [str(r.id) for r in rows]
        max_retries = max(r.notification.max_retries for r in rows)

        # Claim the rows as SENDING (the lease starts at dispatched_at) inside
        # the transaction; the on_commit hook then publishes the broker task. If
        # the commit fails, rows stay PENDING and nothing is published —
        # eliminating the broker-vs-DB duplicate-send race. SENDING rows are
        # excluded from the flush query, so they are not re-claimed until the
        # dispatch task's success/failure callback resolves them to
        # DISPATCHED / DEAD_LETTER (or the reaper reclaims a stale lease).
        now = timezone.now()
        NotificationBuffer.objects.filter(id__in=buffer_ids).update(
            status=BufferStatus.SENDING.value,
            dispatched_at=now,
        )
        transaction.on_commit(
            lambda: _send_clubbed(
                url=first_notification.url,
                body=body,
                headers=headers,
                platform=platform,
                max_retries=max_retries,
                buffer_ids=buffer_ids,
                org_id=org_id,
            )
        )
        return len(rows), len(rows)


# Per-group cap, bound to the renderer's MAX_BATCH_SIZE so the rendered events
# list and the dispatched row set stay in lock-step by construction (raising one
# can no longer silently mark un-rendered rows DISPATCHED). Anything beyond this
# rolls into the next flush tick.
_PROCESS_BUFFER_CAP = MAX_BATCH_SIZE


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["POST"])
def process_notification_buffer(request: HttpRequest) -> JsonResponse:
    """Flush PENDING groups that have hit their flush_after; then GC.

    Algorithm:
    1. GROUP BY (org, url, auth_sig, platform), HAVING MIN(flush_after) <= NOW()
    2. For each group, in its own transaction: lock-skip-locked rows, render,
       mark rows SENDING, on_commit-dispatch a single Celery task whose success /
       failure callbacks move the rows to DISPATCHED / DEAD_LETTER.
    3. Reclaim rows stuck in SENDING past the dispatch lease back to PENDING.
    4. Sweep terminal rows older than NOTIFICATION_BUFFER_RETENTION_DAYS.

    Concurrency: SELECT FOR UPDATE SKIP LOCKED makes parallel calls safe —
    each replica skips groups another worker is already dispatching.
    """
    now = timezone.now()
    groups = list(
        NotificationBuffer.objects.filter(status=BufferStatus.PENDING.value)
        .values("organization_id", "webhook_url", "auth_sig", "platform")
        .annotate(earliest_flush=Min("flush_after"))
        .filter(earliest_flush__lte=now)
    )

    dispatched_groups = 0
    dispatched_rows = 0
    for group in groups:
        try:
            rows, _succeeded = _dispatch_group(
                org_id=group["organization_id"],
                webhook_url=group["webhook_url"],
                auth_sig=group["auth_sig"],
                platform=group["platform"],
            )
        except Exception:
            logger.exception(
                "Failed dispatching group org=%s url_hash=%s",
                group["organization_id"],
                webhook_url_hash(group["webhook_url"]),
            )
            continue
        if rows > 0:
            dispatched_groups += 1
            dispatched_rows += rows

    reclaimed_rows = _reclaim_stale_sending()
    gc_deleted = _gc_terminal_rows()
    return JsonResponse(
        {
            "status": "success",
            "dispatched_groups": dispatched_groups,
            "dispatched_rows": dispatched_rows,
            # DISPATCHED / DEAD_LETTER transitions are async (Celery success /
            # link_error callbacks) and are not reflected in this response.
            "dead_letter_rows": 0,
            "reclaimed_rows": reclaimed_rows,
            "gc_deleted_rows": gc_deleted,
        }
    )
