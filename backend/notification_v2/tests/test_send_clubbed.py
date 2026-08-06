"""Call-site tests for ``_send_clubbed`` / ``_org_identifier`` (UN-3753).

The seam's own routing is covered by ``test_notification_dispatch``; these lock
the two highest-risk regressions at the buffer-flush call site:

1. the two-org-identifier contract — the org **string** id routes the flag, while
   the org **pk** stays in the worker kwargs (swapping them passes every seam test
   yet mis-routes every org to Celery and strands the mark endpoint);
2. failure recovery — a transient/broker error refunds and reverts SENDING rows to
   PENDING, while a permanent PG enqueue error (surfaced as ``PermanentDispatchError``,
   raised only on the PG path) dead-letters instead of retrying forever. A Celery
   send_task failure is an ordinary ``Exception`` → the PENDING path, so flag-off is
   byte-identical.

Mock-based (no broker/DB): patch the module's collaborators.
"""

from __future__ import annotations

from unittest.mock import patch

from django.conf import settings
from notification_v2 import internal_api_views as views
from notification_v2.enums import BufferStatus

_URL = "https://hook.test"
_BODY = {"text": "x"}
_HEADERS = {"Content-Type": "application/json"}
_BUFFER_IDS = ["b1"]


def _send(**overrides):
    kw = {
        "url": _URL,
        "body": _BODY,
        "headers": _HEADERS,
        "platform": "SLACK",
        "max_retries": 3,
        "buffer_ids": _BUFFER_IDS,
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
        # args carry the full webhook invocation, in order.
        assert call["args"] == [_URL, _BODY, _HEADERS, settings.NOTIFICATION_TIMEOUT]
        # buffer_row_ids is what REPLACED the Celery link/link_error callbacks: it is
        # how the worker knows which rows to mark DISPATCHED / DEAD_LETTER. Drop it
        # and every row strands in SENDING until the reclaim lease expires — silent,
        # visible only as a growing SENDING backlog.
        assert call["kwargs"]["buffer_row_ids"] == _BUFFER_IDS


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
        # Guarded on SENDING, reverted to PENDING.
        fkw = buf.objects.filter.call_args.kwargs
        assert fkw["status"] == BufferStatus.SENDING.value
        assert set(fkw["id__in"]) == {"b1", "b2"}
        # Every claimed row goes back to PENDING for the next tick.
        ukw = buf.objects.filter.return_value.update.call_args.kwargs
        assert ukw == {
            "status": BufferStatus.PENDING.value,
            "dispatched_at": None,
        }
        # The refund must be ASSERTED, not merely described in a comment: without it
        # a transient outage burns no attempt (claim +1, refund -1 = net zero), so
        # NOTIFICATION_MAX_DISPATCH_ATTEMPTS is unreachable and a permanently
        # recurring failure re-dispatches every flush tick forever. It is also
        # BOUNDED — only rows still under the limit are refunded, so a failure that
        # keeps recurring eventually ages into the cap.
        refund_qs = buf.objects.filter.return_value.filter
        assert (
            refund_qs.call_args.kwargs["dispatch_attempts__lte"]
            == views.NOTIFICATION_TRANSIENT_REFUND_LIMIT
        )
        refund_kw = refund_qs.return_value.update.call_args.kwargs
        assert set(refund_kw) == {"dispatch_attempts"}
        assert "dispatch_attempts" in str(refund_kw["dispatch_attempts"])  # F(...) - 1

    def test_permanent_pg_error_dead_letters(self):
        # The PG path surfaces a permanent enqueue failure as PermanentDispatchError;
        # only that dead-letters. (A raw ValueError from the Celery path can't occur,
        # and would fall through to the transient PENDING branch, unchanged.)
        with (
            patch.object(views, "_org_identifier", return_value="o"),
            patch.object(
                views,
                "dispatch_webhook_notification",
                side_effect=views.PermanentDispatchError("priority out of range"),
            ),
            patch.object(views, "NotificationBuffer") as buf,
        ):
            _send()
        # Permanent error → terminal DEAD_LETTER, no PENDING revert / refund.
        # The dead-letter update is guarded to only touch rows still SENDING
        # (same clobber-guard the transient-revert path asserts).
        fkw = buf.objects.filter.call_args.kwargs
        assert fkw["status"] == BufferStatus.SENDING.value
        ukw = buf.objects.filter.return_value.update.call_args.kwargs
        assert ukw == {"status": BufferStatus.DEAD_LETTER.value}


class TestOrgIdentifier:
    def test_returns_string_id(self):
        with patch.object(views, "Organization") as org:
            chain = org.objects.filter.return_value.values_list.return_value
            chain.first.return_value = "org-uuid"
            assert views._org_identifier(7) == "org-uuid"
        org.objects.filter.assert_called_once_with(pk=7)

    def test_missing_org_returns_none_and_logs_error(self):
        with (
            patch.object(views, "Organization") as org,
            patch.object(views.logger, "error") as err,
        ):
            chain = org.objects.filter.return_value.values_list.return_value
            chain.first.return_value = None
            assert views._org_identifier(7) is None
        # A dangling FK is a data anomaly: logged at error (Sentry-routed),
        # org-traceable, rather than swallowed.
        err.assert_called_once()
        assert "org_pk" in err.call_args.args[0]
