import hashlib
import json
import logging
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from account_v2.models import Organization
from django.utils import timezone
from unstract.core.data_models import is_failure_run as _core_is_failure_run

from notification_v2.enums import (
    AuthorizationType,
    BufferStatus,
    PlatformType,
)
from notification_v2.models import Notification, NotificationBuffer

logger = logging.getLogger(__name__)


def is_failure_run(execution_status: str | None, failed_files: int | None) -> bool:
    """Backend entry point for the "did this run fail?" rule.

    Delegates to the canonical predicate in ``unstract.core`` (which lives beside
    ``ExecutionStatus`` and is shared with the clubbed renderer) so the dispatch
    filter and the rendered summary can't drift. Kept as the public name here for
    the backend paths: api_v2/notification.py, pipeline_v2/notification.py and
    internal_api_views._apply_failure_filter. The pipeline path ORs an extra
    last_run_status==FAILURE backstop on top for the case where no
    WorkflowExecution can be loaded.
    """
    return _core_is_failure_run(execution_status, failed_files)


# Used as a stable salt-free input for SHA-256 grouping; collisions are
# vanishingly improbable and the digest is never used as a security primitive.
_AUTH_SIG_NONE = ""


def compute_auth_sig(notification: Notification) -> str:
    """SHA-256 hex of (auth_type, auth_key, auth_header) — never raw creds.

    Identical auth configs produce the same sig (so grouping clubs them);
    differing configs split into separate groups. The tuple is JSON-encoded
    before hashing so a literal delimiter byte inside auth_key/header cannot
    cause two distinct tuples to collapse to the same digest.
    """
    raw = json.dumps(
        [
            notification.authorization_type or _AUTH_SIG_NONE,
            notification.authorization_key or _AUTH_SIG_NONE,
            notification.authorization_header or _AUTH_SIG_NONE,
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def webhook_url_hash(url: str | None) -> str:
    """Short, log-safe fingerprint of a webhook URL (first 8 chars of SHA-256)."""
    if not url:
        return "none"
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


def get_org_club_interval_seconds(organization: Organization) -> int:
    """Per-org override of NOTIFICATION_CLUB_INTERVAL, falling back to env default.

    Reads from the generic configuration KV table; returns the env-derived
    default when the org has no override. The value is read at enqueue time
    and baked into the row's flush_after, so changing the override only affects
    rows enqueued after the change.
    """
    # Local import: configuration depends on Django settings at import time
    # and notification_v2.helper is imported during app boot.
    from configuration.enums import ConfigKey
    from configuration.models import Configuration

    return int(
        Configuration.get_value_by_organization(
            ConfigKey.NOTIFICATION_CLUB_INTERVAL, organization
        )
    )


def build_webhook_headers(notification: Notification) -> dict[str, str]:
    """Build HTTP headers for a webhook dispatch from the notification's auth.

    Used by the buffer flush in ``internal_api_views._dispatch_group`` to
    pass live auth headers through to the Celery task.
    """
    headers = {"Content-Type": "application/json"}
    auth_type_raw = (notification.authorization_type or "").upper()
    auth_key = notification.authorization_key
    auth_header = notification.authorization_header
    if auth_type_raw == AuthorizationType.BEARER.value and auth_key:
        headers["Authorization"] = f"Bearer {auth_key}"
    elif auth_type_raw == AuthorizationType.API_KEY.value and auth_key:
        headers["Authorization"] = auth_key
    elif (
        auth_type_raw == AuthorizationType.CUSTOM_HEADER.value
        and auth_header
        and auth_key
    ):
        headers[auth_header] = auth_key
    return headers


def _resolve_organization(notification: Notification) -> Organization | None:
    """Walk pipeline/api FK to find the owning org. Notification has no direct FK."""
    pipeline = notification.pipeline
    if pipeline and pipeline.organization_id:
        return pipeline.organization
    api = notification.api
    if api and api.organization_id:
        return api.organization
    return None


def dispatch_notifications(
    notifications: "Iterable[Notification]",
    payload: dict[str, Any],
    *,
    error_context: str = "",
) -> None:
    """Enqueue every active notification into ``NotificationBuffer``.

    Single dispatch path: each notification produces a buffer row that the
    periodic flush ships as part of a clubbed message. An enqueue failure
    on one row is logged but does not abort the loop — sibling notifications
    still get their chance.

    ``error_context`` lets callers tag failures with their dispatch source
    (pipeline id, api id) for easier triage.
    """
    for notification in notifications:
        try:
            enqueue(notification, payload)
        except Exception:
            # A dropped enqueue means a failure alert may never be delivered —
            # the exact event this feature exists to surface. Emit a metric so
            # the drop is observable, not just buried in a stack trace.
            logger.exception(
                "metric=notification_enqueue_failed_total notification_id=%s "
                "webhook_url_hash=%s%s",
                notification.id,
                webhook_url_hash(notification.url),
                f" context={error_context}" if error_context else "",
            )


def enqueue(notification: Notification, payload: dict[str, Any]) -> NotificationBuffer:
    """Buffer a single execution event for a notification.

    Computes auth_sig and flush_after at write time so existing PENDING rows
    keep their original cadence even if NOTIFICATION_CLUB_INTERVAL or the
    notification's auth changes mid-window. Returns the persisted row.

    Raises ValueError if the notification has no resolvable organization
    (defensive — the FK chain via pipeline/api always provides one in practice).
    """
    organization = _resolve_organization(notification)
    if organization is None:
        raise ValueError(
            f"Notification {notification.id} has no resolvable organization "
            "(neither pipeline nor api FK populated)"
        )

    interval_seconds = get_org_club_interval_seconds(organization)
    flush_after = timezone.now() + timedelta(seconds=interval_seconds)
    auth_sig = compute_auth_sig(notification)
    platform = notification.platform or PlatformType.API.value

    # Stamp a buffered-at timestamp so renderers always have one to humanize.
    # Worker callers already supply one; backend dispatchers
    # (PipelineStatusPayload.to_dict) don't, so default here.
    payload = {
        **payload,
        "timestamp": payload.get("timestamp") or timezone.now().isoformat(),
    }

    buffer_row = NotificationBuffer.objects.create(
        notification=notification,
        organization=organization,
        webhook_url=notification.url,
        payload=payload,
        platform=platform,
        auth_sig=auth_sig,
        flush_after=flush_after,
        status=BufferStatus.PENDING.value,
    )

    # Structured log: org + URL fingerprint only — never the raw URL or any
    # part of the auth tuple. Downstream metrics consumers grep on metric=.
    logger.info(
        "metric=notification_buffer_enqueued_total platform=%s org_id=%s "
        "webhook_url_hash=%s notification_id=%s buffer_id=%s flush_after=%s",
        platform,
        organization.organization_id,
        webhook_url_hash(notification.url),
        notification.id,
        buffer_row.id,
        flush_after.isoformat(),
    )
    return buffer_row
