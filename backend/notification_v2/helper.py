import hashlib
import logging
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from account_v2.models import Organization
from django.utils import timezone

from notification_v2.enums import (
    AuthorizationType,
    BufferStatus,
    DeliveryMode,
    NotificationType,
    PlatformType,
)
from notification_v2.models import Notification, NotificationBuffer
from notification_v2.provider.notification_provider import NotificationProvider
from notification_v2.provider.registry import get_notification_provider

logger = logging.getLogger(__name__)

# Used as a stable salt-free input for SHA-256 grouping; collisions are
# vanishingly improbable and the digest is never used as a security primitive.
_AUTH_SIG_NONE = ""


def compute_auth_sig(notification: Notification) -> str:
    """SHA-256 hex of (auth_type + auth_key + auth_header) — never raw creds.

    Identical auth configs produce the same sig (so grouping clubs them);
    differing configs split into separate groups.
    """
    raw = "|".join(
        [
            notification.authorization_type or _AUTH_SIG_NONE,
            notification.authorization_key or _AUTH_SIG_NONE,
            notification.authorization_header or _AUTH_SIG_NONE,
        ]
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
    and baked into the row's flush_after — see mfbt §EC-2 / §EC-8: changing
    the override only affects rows enqueued after the change.
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

    Mirrors the logic in ``provider/webhook/webhook.py`` and the worker-side
    ``get_webhook_headers`` so the clubbed dispatcher and the immediate path
    produce identical headers for the same auth config.
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


def split_by_delivery_mode(
    notifications: "Iterable[Notification]",
) -> tuple[list[Notification], list[Notification]]:
    """Partition into (IMMEDIATE, BATCHED). Unknown modes default to IMMEDIATE."""
    immediate: list[Notification] = []
    batched: list[Notification] = []
    for n in notifications:
        if n.delivery_mode == DeliveryMode.BATCHED.value:
            batched.append(n)
        else:
            immediate.append(n)
    return immediate, batched


def dispatch_with_delivery_mode(
    notifications: "Iterable[Notification]",
    payload: dict[str, Any],
    *,
    error_context: str = "",
) -> None:
    """Single-call entry point that splits IMMEDIATE / BATCHED and dispatches.

    IMMEDIATE rows fire synchronously via NotificationHelper. BATCHED rows
    enqueue into NotificationBuffer; an enqueue failure is logged but does
    not abort the loop — other notifications still get their chance.

    ``error_context`` lets callers tag failures with their dispatch source
    (pipeline id, api id) for easier triage.
    """
    immediate, batched = split_by_delivery_mode(notifications)
    if immediate:
        NotificationHelper.send_notification(notifications=immediate, payload=payload)
    for notification in batched:
        try:
            enqueue(notification, payload)
        except Exception:
            logger.exception(
                "Failed to enqueue BATCHED notification %s%s",
                notification.id,
                f" ({error_context})" if error_context else "",
            )


def enqueue(notification: Notification, payload: dict[str, Any]) -> NotificationBuffer:
    """Buffer a single execution event for a BATCHED notification.

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


class NotificationHelper:
    @classmethod
    def send_notification(cls, notifications: list[Notification], payload: Any) -> None:
        """Dispatch IMMEDIATE notifications via the registered provider.

        Iterates over notifications, resolves the provider for each
        (notification_type, platform) pair, and fires the webhook task. BATCHED
        notifications must be routed to ``enqueue()`` instead — callers branch
        on ``notification.delivery_mode`` before reaching this method.

        Args:
            notifications: Active Notification rows to dispatch synchronously.
            payload: Provider-specific payload (typically a dict).
        """
        for notification in notifications:
            if notification.delivery_mode == DeliveryMode.BATCHED.value:
                # Callers should not reach here for BATCHED — log loudly so
                # routing regressions are visible without breaking dispatch.
                logger.warning(
                    "BATCHED notification %s reached IMMEDIATE dispatch path; "
                    "skipping. Caller must branch on delivery_mode.",
                    notification.id,
                )
                continue
            notification_type = NotificationType(notification.notification_type)
            platform_type = PlatformType(notification.platform)
            try:
                notification_provider = get_notification_provider(
                    notification_type, platform_type
                )
                notifier: NotificationProvider = notification_provider(
                    notification=notification, payload=payload
                )
                notifier.send()
                logger.info("Sending notification to %s", notification)
            except ValueError as e:
                logger.error(
                    "Error in notification type %s and platform %s for "
                    "notification %s: %s",
                    notification_type,
                    platform_type,
                    notification,
                    e,
                )
