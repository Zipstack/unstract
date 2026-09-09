"""Tests for the thin dashboard-metrics proxy tasks (UN-3796).

The tasks themselves do nothing but call a backend internal endpoint, so what is worth
pinning is the contract around that call: the registered names (a mismatch means the PG
consumer drops the message as an unknown task — the failure mode with no error at the
enqueue site), the request shape, and the failure posture.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import via the PACKAGE, matching `scheduler/tasks.py`'s
# `from scheduler import dashboard_metrics_tasks` (OSS 6397dd578) — which is the form
# BOTH runtime mechanisms converge on: worker.py's by-path load of tasks.py still
# resolves that import against /app, so `scheduler.dashboard_metrics_tasks` is the
# single module object either way.
#
# The bare `import dashboard_metrics_tasks` used here previously mirrored only the
# by-path load, and once tasks.py started importing the package form the two coexisted
# as SEPARATE module objects with separate Celery registrations. Patching one left the
# other live, so a test that believed it had mocked the HTTP client made a REAL request
# and failed on DNS — but only when some earlier test in the run had already imported
# `scheduler.tasks`, which is why it looked like flakiness rather than a wiring bug.
_WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(_WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKERS_ROOT))

from scheduler import dashboard_metrics_tasks as dmt  # noqa: E402

_ENV = {
    "INTERNAL_API_BASE_URL": "http://backend:8000/internal",
    "INTERNAL_SERVICE_API_KEY": "test-key",
}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)


class TestRegistration:
    """The names must match the Beat rows exactly, or the mirror's verbatim copy
    produces a message no consumer can resolve — silently dropped as poison.
    """

    @pytest.mark.parametrize(
        "name,func",
        [
            ("dashboard_metrics.aggregate_from_sources", "dashboard_metrics_aggregate"),
            ("dashboard_metrics.cleanup_hourly_data", "dashboard_metrics_cleanup_hourly"),
            ("dashboard_metrics.cleanup_daily_data", "dashboard_metrics_cleanup_daily"),
        ],
    )
    def test_task_is_registered_under_the_beat_name(self, name, func):
        assert getattr(dmt, func).name == name


class TestCallContract:
    def test_aggregate_posts_to_the_aggregate_endpoint(self):
        with patch.object(dmt, "_call_internal", return_value={"success": True}) as call:
            dmt.dashboard_metrics_aggregate()
        assert call.call_args[0][0] == "v1/dashboard-metrics/aggregate/"

    @pytest.mark.parametrize("tier", ["hourly", "daily_monthly", "all"])
    def test_aggregate_forwards_the_tier_from_the_schedule_row(self, tier):
        """UN-3974: the PG scheduler hands a row's task_kwargs over as **kwargs, so the
        tier arrives here and has to reach the backend in the request body.

        This is the leg that fails quietly. Drop the forwarding and every schedule still
        fires, the endpoint still returns 200, and every other test here still passes —
        but both rows run the default tier, so daily and monthly quietly go back to
        being recomputed every 15 minutes.
        """
        with patch.object(dmt, "_call_internal", return_value={"success": True}) as call:
            dmt.dashboard_metrics_aggregate(tier=tier)
        assert call.call_args.kwargs["body"] == {"tier": tier}

    def test_aggregate_passes_the_source_window_through(self):
        # UN-3973: the reconciliation row carries this; dropping it here silently
        # reverts the pass to the narrow window it exists to widen.
        with patch.object(dmt, "_call_internal", return_value={"success": True}) as call:
            dmt.dashboard_metrics_aggregate(source_window_days=7)
        assert call.call_args.kwargs["body"] == {"source_window_days": 7}

    def test_aggregate_omits_the_body_when_neither_is_given(self):
        # Rows written before 0006 carry no tier kwarg; the backend default then applies,
        # which is every tier rather than none.
        with patch.object(dmt, "_call_internal", return_value={"success": True}) as call:
            dmt.dashboard_metrics_aggregate()
        assert call.call_args.kwargs["body"] is None

    @pytest.mark.parametrize(
        "func,path",
        [
            ("dashboard_metrics_cleanup_hourly", "v1/dashboard-metrics/cleanup/hourly/"),
            ("dashboard_metrics_cleanup_daily", "v1/dashboard-metrics/cleanup/daily/"),
        ],
    )
    def test_cleanup_passes_retention_through(self, func, path):
        with patch.object(dmt, "_call_internal", return_value={"deleted": 1}) as call:
            getattr(dmt, func)(retention_days=45)
        assert call.call_args[0][0] == path
        assert call.call_args.kwargs["body"] == {"retention_days": 45}

    def test_cleanup_omits_body_when_no_retention_given(self):
        # The backend then applies the same default the Beat kwargs carry, so an
        # unspecified call matches the Celery path rather than inventing a value here.
        with patch.object(dmt, "_call_internal", return_value={}) as call:
            dmt.dashboard_metrics_cleanup_hourly()
        assert call.call_args.kwargs["body"] is None

    def test_lock_held_result_is_surfaced_not_swallowed(self, caplog):
        # A permanently leaked lock otherwise looks like 96 successful no-op runs a day.
        with patch.object(
            dmt,
            "_call_internal",
            return_value={"success": True, "skipped": True, "reason": "lock_held"},
        ):
            result = dmt.dashboard_metrics_aggregate()
        assert result["skipped"] is True


class TestTheReconciliationKwargSurvives:
    """0005 declares a row against this same task path carrying source_window_days.

    The PG scheduler copies task_kwargs verbatim into the payload, so a proxy that
    does not accept it raises TypeError per tick — not covered by autoretry_for, and
    dropped at MAX_ATTEMPTS=1. The gap-repair pass simply never runs.
    """

    _DECLARED = [{}, {"tier": "hourly"}, {"source_window_days": 7}]

    @pytest.mark.parametrize("kwargs", _DECLARED)
    def test_every_scheduled_kwarg_set_binds(self, kwargs) -> None:
        named = {
            p.name
            for p in inspect.signature(dmt.dashboard_metrics_aggregate).parameters.values()
            if p.kind is not inspect.Parameter.VAR_KEYWORD
        }
        # Named parameters only — `**_ignored` makes bind() accept anything.
        assert not set(kwargs) - named

    def test_the_source_window_reaches_the_endpoint(self) -> None:
        with patch.object(dmt, "_call_internal", return_value={}) as call:
            dmt.dashboard_metrics_aggregate(source_window_days=7)
        assert call.call_args.kwargs["body"] == {"source_window_days": 7}

    def test_both_kwargs_travel_together(self) -> None:
        with patch.object(dmt, "_call_internal", return_value={}) as call:
            dmt.dashboard_metrics_aggregate(tier="hourly", source_window_days=7)
        assert call.call_args.kwargs["body"] == {
            "tier": "hourly",
            "source_window_days": 7,
        }

    def test_omitting_both_sends_no_body(self) -> None:
        # The backend then applies its own defaults rather than ones invented here.
        with patch.object(dmt, "_call_internal", return_value={}) as call:
            dmt.dashboard_metrics_aggregate()
        assert call.call_args.kwargs["body"] is None


class TestInternalCall:
    def _response(self, status_code=200, payload=None):
        r = MagicMock()
        r.status_code = status_code
        r.json.return_value = payload if payload is not None else {"ok": True}
        r.text = "boom"
        return r

    def test_sends_bearer_auth_and_never_an_org_header(self):
        # X-Organization-ID would make the middleware scope every ORM read in these
        # global aggregations to one tenant.
        with patch.object(dmt.httpx, "Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = self._response()
            dmt._call_internal("v1/x/")
        headers = client.request.call_args.kwargs["headers"]
        assert headers == {"Authorization": "Bearer test-key"}
        assert not any(h.lower() == "x-organization-id" for h in headers)

    def test_timeout_outlasts_the_server_side_ceiling(self):
        # The ceiling that matters is gunicorn's --timeout 600, not the task's Celery
        # time_limit=660 (no Celery worker runs it on this path). The client must sit
        # ABOVE 600 so a long run surfaces the server's error rather than our own
        # timeout — which would look like a network fault and hide the real cause.
        with patch.object(dmt.httpx, "Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = self._response()
            dmt._call_internal("v1/x/")
        assert client.request.call_args.kwargs["timeout"] > 600

    def test_non_200_raises(self):
        with patch.object(dmt.httpx, "Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = self._response(status_code=500)
            with pytest.raises(RuntimeError, match="HTTP 500"):
                dmt._call_internal("v1/x/")

    @pytest.mark.parametrize(
        "missing", ["INTERNAL_API_BASE_URL", "INTERNAL_SERVICE_API_KEY"]
    )
    def test_missing_config_raises_rather_than_returning_falsy(
        self, monkeypatch, missing
    ):
        # Deliberately different from process_log_history.py, which returns False: that
        # runs under a bash loop with no other channel. Here raising is what marks the
        # message failed and gets it logged.
        monkeypatch.delenv(missing)
        with pytest.raises(RuntimeError, match=missing):
            dmt._call_internal("v1/x/")


class TestTheRunSummaryReachesTheLog:
    """The proxy's log line is the only view of a run on the PG transport.

    Every branch below existed with no test: deleting all of them left the whole
    workers suite green, which is the same as having no operator signal at all.
    """

    def _run(self, caplog, result):
        with caplog.at_level("WARNING"):
            with patch.object(dmt, "_call_internal", return_value=result):
                dmt.dashboard_metrics_aggregate()
        return caplog.text

    def test_an_empty_prefilter_reports_the_rows_the_rollup_still_wrote(self, caplog):
        text = self._run(
            caplog,
            {
                "success": True,
                "skipped_reason": "no_active_orgs",
                "tier": "daily_monthly",
                "monthly": {"upserted": 7},
            },
        )
        assert "no_active_orgs" in text
        assert "rows written: 7" in text

    def test_an_error_is_reported_even_alongside_an_empty_prefilter(self, caplog):
        """The two co-occur: the rollup is org-agnostic and runs when the loop did not.

        Reported as alternatives, the failure hides behind a benign "no active orgs".
        """
        text = self._run(
            caplog,
            {
                "success": False,
                "skipped_reason": "no_active_orgs",
                "errors": 1,
                "organizations_processed": 0,
                "tier": "daily_monthly",
                "monthly": {"upserted": 0, "failed": True},
            },
        )
        assert "no_active_orgs" in text
        assert "1 error(s)" in text

    def test_a_preserved_monthly_total_is_named_and_not_called_a_lowering(self, caplog):
        """The backend KEPT these months; the worker used to say it lowered them.

        Naming the month was all this asserted, so an inverted verb passed. The two
        processes then emitted opposite remediations for one event — and on the PG
        transport this line is what on-call sees first. "Lowered" points at a
        rollback; the fix is a backfill.
        """
        text = self._run(
            caplog,
            {
                "success": True,
                "tier": "daily_monthly",
                "monthly": {
                    "upserted": 3,
                    "needs_daily_repair": ["2026-08 (org 3)"],
                },
            },
        )
        assert "2026-08 (org 3)" in text
        assert "unchanged" in text and "backfill_metrics" in text
        assert "lowered existing" not in text

    def test_an_incomplete_daily_tier_is_named(self, caplog):
        """Independent of the above: no stored total, so nothing was preserved."""
        text = self._run(
            caplog,
            {
                "success": True,
                "tier": "daily_monthly",
                "monthly": {
                    "upserted": 3,
                    "incomplete_daily_coverage": ["2026-03 (8/9 days)"],
                },
            },
        )
        assert "2026-03 (8/9 days)" in text
        assert "under-counted" in text

    def test_a_clean_run_that_wrote_nothing_is_still_reported(self, caplog):
        """The regression signature of narrowing the source window: work to do, no
        error, nothing written. It passes every other branch silently.
        """
        text = self._run(
            caplog,
            {"success": True, "tier": "daily_monthly", "organizations_processed": 4},
        )
        assert "wrote no rows" in text

    def test_a_normal_run_logs_no_warning(self, caplog):
        """The control: the arms above must not fire on a healthy run."""
        text = self._run(
            caplog,
            {
                "success": True,
                "tier": "hourly",
                "organizations_processed": 4,
                "hourly": {"upserted": 12},
            },
        )
        assert text.strip() == ""


class TestAnUnknownKwargDoesNotKillTheRun:
    """The schedule rows and this consumer ship in different images.

    A migration in the backend image can write a kwarg into a row while a
    worker-unified pod is still on the previous image. The PG scheduler copies
    task_kwargs verbatim into the payload and the consumer applies them, so a
    signature that rejects the unknown key raises TypeError — not covered by
    autoretry_for and dropped at MAX_ATTEMPTS=1. The */15 rows survive that on
    their next tick; the once-daily reconciliation row does not.
    """

    def test_an_unrecognised_kwarg_is_accepted_and_not_forwarded(self):
        with patch.object(dmt, "_call_internal", return_value={"success": True}) as call:
            dmt.dashboard_metrics_aggregate(tier="hourly", some_future_kwarg=1)

        assert call.call_args.kwargs["body"] == {"tier": "hourly"}


class TestCleanupFailuresReachTheLog:
    """`_log_if_failed` was added with no test, in the same file and commit as the
    branches that did get one. The backend answers 200 with success: False, so this
    is the only place a permanently failing retention delete becomes visible here.
    """

    def _run(self, caplog, task, result):
        with caplog.at_level("WARNING"):
            with patch.object(dmt, "_call_internal", return_value=result):
                task()
        return caplog.text

    def test_a_failed_cleanup_is_reported(self, caplog):
        text = self._run(
            caplog,
            dmt.dashboard_metrics_cleanup_hourly,
            {"success": False, "error": "deadlock detected"},
        )
        assert "did not complete" in text
        assert "deadlock detected" in text

    def test_a_successful_cleanup_is_silent(self, caplog):
        """The control: it reports failure, not every run."""
        text = self._run(
            caplog, dmt.dashboard_metrics_cleanup_daily, {"success": True, "deleted": 4}
        )
        assert text.strip() == ""


class TestTheDiagnosticBlindSpotIsReported:
    """A check that could not run must not read as a check that found nothing."""

    def test_an_unavailable_check_is_named(self, caplog):
        with caplog.at_level("WARNING"):
            with patch.object(
                dmt,
                "_call_internal",
                return_value={
                    "success": True,
                    "tier": "daily_monthly",
                    "monthly": {"upserted": 7, "lowered_check": "unavailable"},
                },
            ):
                dmt.dashboard_metrics_aggregate()
        # "would lower", not "lowered": the check never ran, so nothing was lowered
        # — the same past-tense slip the payload rename removed from the other arm.
        assert "could not check whether the rollup would lower" in caplog.text
        assert "rollup lowered" not in caplog.text

    def test_a_failed_rollup_is_named_as_fleet_wide(self, caplog):
        """Distinct from a per-org metric error, which reads the same otherwise."""
        with caplog.at_level("WARNING"):
            with patch.object(
                dmt,
                "_call_internal",
                return_value={
                    "success": False,
                    "errors": 1,
                    "organizations_processed": 3,
                    "tier": "daily_monthly",
                    "monthly": {"upserted": 0, "failed": True},
                },
            ):
                dmt.dashboard_metrics_aggregate()
        assert "every tenant's monthly tier is stale" in caplog.text
