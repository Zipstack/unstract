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
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from backend.celery_service import app as celery_app
from notification_v2.clubbed_renderer import render_clubbed_message
from notification_v2.enums import BufferStatus, DeliveryMode
from notification_v2.helper import (
    build_webhook_headers,
    enqueue,
    get_org_club_interval_seconds,
    webhook_url_hash,
)
from notification_v2.models import Notification, NotificationBuffer

logger = logging.getLogger(__name__)

# Constants for error messages
INTERNAL_SERVER_ERROR_MSG = "Internal server error"

_FAILURE_STATUSES = {ExecutionStatus.ERROR.value, ExecutionStatus.STOPPED.value}


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

    Mirrors the dispatch-side rule in backend/api_v2/notification.py and
    backend/pipeline_v2/notification.py so both code paths agree on what
    counts as a failure (status ∈ {ERROR, STOPPED} OR any file errored).

    No execution → no filter, preserving legacy "return every active row"
    behavior for callers that don't pass execution_id.
    """
    if execution is None:
        return notifications_qs
    failed_files = execution.failed_files or 0
    is_failure = execution.status in _FAILURE_STATUSES or failed_files > 0
    if not is_failure:
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
        # Drives the worker-side IMMEDIATE-vs-BATCHED branch in
        # workers/shared/patterns/notification/helper.py.
        "delivery_mode": n.delivery_mode,
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


# Required fields on the enqueue endpoint body. Worker-side serialization
# guarantees these — keep this list in sync with
# workers/shared/patterns/notification/helper.py.
_ENQUEUE_REQUIRED_FIELDS = (
    "notification_id",
    "execution_id",
    "pipeline_id",
    "pipeline_name",
    "status",
    "platform",
)


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["POST"])
def enqueue_notification_buffer(request: HttpRequest) -> JsonResponse:
    """Buffer one execution event from a callback worker.

    Worker code is model-free: it forwards a notification_id + structured
    payload here and lets the backend write the NotificationBuffer row.
    Rejects rows whose source notification is not BATCHED so a worker
    routing bug cannot silently divert IMMEDIATE traffic into the buffer.
    """
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON body"}, status=400
        )

    missing = [f for f in _ENQUEUE_REQUIRED_FIELDS if not body.get(f)]
    if missing:
        return JsonResponse(
            {
                "status": "error",
                "message": f"Missing required fields: {', '.join(missing)}",
            },
            status=400,
        )

    try:
        notification = Notification.objects.get(id=body["notification_id"])
    except Notification.DoesNotExist:
        return JsonResponse(
            {"status": "error", "message": "Notification not found"}, status=404
        )

    if notification.delivery_mode != DeliveryMode.BATCHED.value:
        # Hard-fail rather than silently auto-correcting — surfaces worker
        # routing regressions instead of letting them drain into the buffer.
        return JsonResponse(
            {
                "status": "error",
                "message": (
                    "Notification delivery_mode is not BATCHED; refuse to enqueue"
                ),
            },
            status=409,
        )

    # type / timestamp / additional_data stay optional during rollout — older
    # worker builds that don't forward them still produce a usable row
    # (renderer falls back to "Type: —" / no Additional Data line).
    payload = {
        "type": body.get("type", ""),
        "execution_id": body["execution_id"],
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
    """Delete DISPATCHED / DEAD_LETTER rows older than the retention window.

    PENDING rows are intentionally untouched regardless of age — they
    represent live work the flush job still owns.
    """
    cutoff = timezone.now() - timedelta(days=settings.NOTIFICATION_BUFFER_RETENTION_DAYS)
    deleted_count, _ = NotificationBuffer.objects.filter(
        status__in=[BufferStatus.DISPATCHED.value, BufferStatus.DEAD_LETTER.value],
        created_at__lt=cutoff,
    ).delete()
    return int(deleted_count)


def _dispatch_group(
    org_id: Any,
    webhook_url: str,
    auth_sig: str,
) -> tuple[int, int]:
    """Dispatch a single (org, url, auth_sig) group; returns (rows, succeeded).

    Caller already filtered groups to MIN(flush_after) <= now. Locks rows
    with SKIP LOCKED so a sibling replica skips them rather than blocking.
    Re-fetches the source Notification each time for live auth (record may
    have been edited between enqueue and flush).
    """
    with transaction.atomic():
        rows = list(
            NotificationBuffer.objects.select_for_update(skip_locked=True)
            .filter(
                status=BufferStatus.PENDING.value,
                organization_id=org_id,
                webhook_url=webhook_url,
                auth_sig=auth_sig,
            )
            .order_by("created_at")[:_PROCESS_BUFFER_CAP]
        )
        if not rows:
            # Either another replica claimed the rows (SKIP LOCKED) or they
            # transitioned out of PENDING between the GROUP BY scan and the
            # row-level lock. Either way: nothing to do here.
            return 0, 0

        # Live auth — read from the FIRST row's notification. If multiple
        # notifications collide on (url, auth_sig) we have, by definition,
        # identical auth, so this is safe.
        first_notification = rows[0].notification
        platform = rows[0].platform
        payloads = [r.payload for r in rows]
        # Per-org interval read here is cosmetic — used only for the
        # `interval_minutes` field in the rendered message body. The
        # cadence-controlling read happened at enqueue time and is
        # already baked into each row's flush_after (mfbt §EC-2).
        interval_seconds = get_org_club_interval_seconds(rows[0].organization)
        body = render_clubbed_message(payloads, platform, interval_seconds)
        headers = build_webhook_headers(first_notification)

        buffer_ids = [str(r.id) for r in rows]
        try:
            celery_app.send_task(
                "send_webhook_notification",
                args=[
                    first_notification.url,
                    body,
                    headers,
                    settings.NOTIFICATION_TIMEOUT,
                ],
                kwargs={
                    "max_retries": first_notification.max_retries,
                    "retry_delay": 10,
                    "platform": platform,
                },
                queue="notifications",
                link_error=celery_app.signature(
                    "notification_v2.mark_buffer_dead_letter",
                    kwargs={"buffer_row_ids": buffer_ids},
                ),
            )
        except Exception:
            # Broker hiccup — leave rows PENDING for the next tick rather
            # than mark them DEAD_LETTER. `exception` keeps stack context.
            logger.exception(
                "Broker dispatch failed for group org=%s url_hash=%s",
                org_id,
                webhook_url_hash(webhook_url),
            )
            return 0, 0

        now = timezone.now()
        NotificationBuffer.objects.filter(id__in=buffer_ids).update(
            status=BufferStatus.DISPATCHED.value,
            dispatched_at=now,
        )
        logger.info(
            "metric=notification_batch_dispatched_total platform=%s result=success "
            "org_id=%s webhook_url_hash=%s rows=%d",
            platform,
            org_id,
            webhook_url_hash(webhook_url),
            len(rows),
        )
        return len(rows), len(rows)


# Per-group cap; matches the renderer's MAX_BATCH_SIZE so the rendered
# events list and the dispatched row set stay in lock-step. Anything beyond
# this rolls into the next flush tick.
_PROCESS_BUFFER_CAP = 500


@csrf_exempt  # Safe: Internal API with Bearer token auth, service-to-service only
@require_http_methods(["POST"])
def process_notification_buffer(request: HttpRequest) -> JsonResponse:
    """Flush PENDING groups that have hit their flush_after; then GC.

    Algorithm:
    1. GROUP BY (org, url, auth_sig), HAVING MIN(flush_after) <= NOW()
    2. For each group, in its own transaction: lock-skip-locked rows,
       render, dispatch a single Celery task, mark rows DISPATCHED.
    3. Sweep terminal rows older than NOTIFICATION_BUFFER_RETENTION_DAYS.

    Concurrency: SELECT FOR UPDATE SKIP LOCKED makes parallel calls safe —
    each replica skips groups another worker is already dispatching.
    """
    now = timezone.now()
    groups = list(
        NotificationBuffer.objects.filter(status=BufferStatus.PENDING.value)
        .values("organization_id", "webhook_url", "auth_sig")
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

    gc_deleted = _gc_terminal_rows()
    return JsonResponse(
        {
            "status": "success",
            "dispatched_groups": dispatched_groups,
            "dispatched_rows": dispatched_rows,
            # DEAD_LETTER transitions are async (Celery link_error) — this
            # response only covers transitions visible to this request.
            "dead_letter_rows": 0,
            "gc_deleted_rows": gc_deleted,
        }
    )
