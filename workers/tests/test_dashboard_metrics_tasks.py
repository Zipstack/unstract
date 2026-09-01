"""Tests for the thin dashboard-metrics proxy tasks (UN-3796).

The tasks themselves do nothing but call a backend internal endpoint, so what is worth
pinning is the contract around that call: the registered names (a mismatch means the PG
consumer drops the message as an unknown task — the failure mode with no error at the
enqueue site), the request shape, and the failure posture.
"""

from __future__ import annotations

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

    def test_aggregate_omits_the_body_when_no_tier_is_given(self):
        # Pre-0005 rows carry no tier kwarg; the backend's default then applies, which
        # is every tier rather than none.
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
    def test_missing_config_raises_rather_than_returning_falsy(self, monkeypatch, missing):
        # Deliberately different from process_log_history.py, which returns False: that
        # runs under a bash loop with no other channel. Here raising is what marks the
        # message failed and gets it logged.
        monkeypatch.delenv(missing)
        with pytest.raises(RuntimeError, match=missing):
            dmt._call_internal("v1/x/")
