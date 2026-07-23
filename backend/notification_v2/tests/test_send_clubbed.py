"""Call-site tests for ``_send_clubbed`` / ``_org_identifier`` (UN-3753).

The seam's own routing is covered by ``test_notification_dispatch``; these lock
the two highest-risk regressions at the buffer-flush call site:

1. the two-org-identifier contract — the org **string** id routes the flag, while
   the org **pk** stays in the worker kwargs (swapping them passes every seam test
   yet mis-routes every org to Celery and strands the mark endpoint);
2. failure recovery — a transient/broker error refunds and reverts SENDING rows to
   PENDING, while a permanent (ValueError/TypeError) enqueue error dead-letters
   instead of retrying forever.

Mock-based (no broker/DB): patch the module's collaborators.
"""

from __future__ import annotations

from unittest.mock import patch

from notification_v2 import internal_api_views as views
from notification_v2.enums import BufferStatus


def _send(**overrides):
    kw = {
        "url": "https://hook.test",
        "body": {"text": "x"},
        "headers": {"Content-Type": "application/json"},
        "platform": "SLACK",
        "max_retries": 3,
        "buffer_ids": ["b1"],
        "org_id": 7,
    }
    kw.update(overrides)
    views._send_clubbed(**kw)


class TestSendClubbedOrgContract:
    def test_routes_string_id_and_keeps_pk_in_kwargs(self):
        with (
            patch.object(views, "_org_identifier", return_value="org-str-id") as ident,
            patch.object(views, "dispatch_webhook_notification") as seam,
        ):
            _send(org_id=7)
        ident.assert_called_once_with(7)
        call = seam.call_args.kwargs
        # Routing uses the STRING id; the worker buffer-mark contract keeps the PK.
        assert call["org_string_id"] == "org-str-id"
        assert call["kwargs"]["organization_id"] == 7
        assert call["queue"] == "notifications"


class TestSendClubbedFailureRecovery:
    def test_transient_failure_reverts_sending_rows_to_pending(self):
        with (
            patch.object(views, "_org_identifier", return_value="o"),
            patch.object(
                views,
                "dispatch_webhook_notification",
                side_effect=RuntimeError("broker down"),
            ),
            patch.object(views, "NotificationBuffer") as buf,
        ):
            _send(buffer_ids=["b1", "b2"])
        # Guarded on SENDING, reverted to PENDING (attempt refunded).
        fkw = buf.objects.filter.call_args.kwargs
        assert fkw["status"] == BufferStatus.SENDING.value
        assert set(fkw["id__in"]) == {"b1", "b2"}
        ukw = buf.objects.filter.return_value.update.call_args.kwargs
        assert ukw["status"] == BufferStatus.PENDING.value
        assert ukw["dispatched_at"] is None

    def test_permanent_error_dead_letters(self):
        with (
            patch.object(views, "_org_identifier", return_value="o"),
            patch.object(
                views,
                "dispatch_webhook_notification",
                side_effect=ValueError("priority out of range"),
            ),
            patch.object(views, "NotificationBuffer") as buf,
        ):
            _send()
        # Permanent error → terminal DEAD_LETTER, no PENDING revert / refund.
        ukw = buf.objects.filter.return_value.update.call_args.kwargs
        assert ukw == {"status": BufferStatus.DEAD_LETTER.value}


class TestOrgIdentifier:
    def test_returns_string_id(self):
        with patch.object(views, "Organization") as org:
            chain = org.objects.filter.return_value.values_list.return_value
            chain.first.return_value = "org-uuid"
            assert views._org_identifier(7) == "org-uuid"
        org.objects.filter.assert_called_once_with(pk=7)

    def test_missing_org_returns_none_and_warns(self):
        with (
            patch.object(views, "Organization") as org,
            patch.object(views.logger, "warning") as warn,
        ):
            chain = org.objects.filter.return_value.values_list.return_value
            chain.first.return_value = None
            assert views._org_identifier(7) is None
        # A dangling FK is logged (org-traceable) rather than swallowed.
        warn.assert_called_once()
        assert "org_pk" in warn.call_args.args[0]
