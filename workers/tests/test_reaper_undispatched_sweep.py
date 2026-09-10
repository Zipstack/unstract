"""The reaper's trigger for the backend undispatched-execution sweep.

The sweep's *logic* lives in the backend (it touches WorkflowExecution, the rate
limiter and API storage — none of which a worker may reach). What the reaper
contributes is leader election, so exactly one instance runs it. These pin the
wiring, which is the part the backend tests cannot see:

  * it is CADENCE-GATED, not per-tick — the rows are already older than the grace
    period, so running it every 5s would be pure DB load;
  * a failure is SWALLOWED — unlike barrier recovery, this cleans up work that is
    already dead, and discarding the connection would defer schedule dispatch, which
    serves live traffic.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from queue_backend.pg_queue import reaper as reaper_mod


def _reaper_with(api_client):
    """A PgReaper stand-in exposing only what _sweep_undispatched_executions uses.

    Built with __new__ so no DB/lease/metrics registry is required; the two collaborators
    the method actually touches are injected.
    """
    r = reaper_mod.PgReaper.__new__(reaper_mod.PgReaper)
    r._get_api_client = lambda: api_client  # type: ignore[method-assign]
    r._metrics = MagicMock()
    return r


class TestTheTriggerIsWiredToTheBackend:
    def test_it_calls_the_backend_sweep(self):
        api = MagicMock()
        # The REAL client returns the parsed body verbatim (typed `-> dict[str, Any]`),
        # not an object with `.data`. This fixture used to be SimpleNamespace(data=...),
        # a shape nothing in the call chain produces — so it asserted inc(3) while
        # production read `.data` off a dict and always incremented by 0. The test
        # passed against a fiction and hid a dead metric.
        api.sweep_undispatched_executions.return_value = {"swept": 3}
        r = _reaper_with(api)
        r._sweep_undispatched_executions()
        api.sweep_undispatched_executions.assert_called_once_with()
        # Counted by how many were recovered, not "one sweep ran" — the rate is the
        # signal that requests are dying before dispatch.
        r._metrics.undispatched_swept.inc.assert_called_once_with(3)

    def test_a_zero_result_is_not_an_error(self):
        """The steady state. Must stay quiet, not log every 5 minutes forever."""
        api = MagicMock()
        api.sweep_undispatched_executions.return_value = {"swept": 0}
        r = _reaper_with(api)
        r._sweep_undispatched_executions()  # no raise
        # A zero must NOT touch the counter: inc(0) is harmless but a nonzero rate is
        # the alert signal, so keep the series clean.
        r._metrics.undispatched_swept.inc.assert_not_called()

    def test_a_missing_or_odd_payload_does_not_raise(self):
        """A backend on an older image returns no `swept` key — that must not take
        down a leader tick that also dispatches schedules.
        """
        for payload in (None, {}, {"unexpected": 1}, SimpleNamespace(data={"swept": 9})):
            api = MagicMock()
            api.sweep_undispatched_executions.return_value = payload
            _reaper_with(api)._sweep_undispatched_executions()  # no raise


class TestAFailureCannotBreakTheTick:
    def test_an_api_error_is_swallowed(self):
        """Barrier recovery re-raises and discards the connection because a stranded
        RUNNING execution is urgent. This is the opposite case — the executions are
        already dead — and raising here would abort the tick and defer schedule
        dispatch for live traffic. Cleanup must never outrank scheduling.
        """
        api = MagicMock()
        api.sweep_undispatched_executions.side_effect = RuntimeError("backend down")
        r = _reaper_with(api)
        r._sweep_undispatched_executions()  # must not raise
        # Swallowed, but counted — otherwise a persistently failing sweep is invisible
        # and PENDING rows accumulate unrecovered.
        r._metrics.undispatched_sweep_failures.inc.assert_called_once()

    def test_the_failure_is_logged_so_it_is_not_silent(self):
        """Swallowed is not the same as hidden — a persistently failing sweep means
        PENDING rows accumulate, and that has to be visible.
        """
        api = MagicMock()
        api.sweep_undispatched_executions.side_effect = RuntimeError("backend down")
        with patch.object(reaper_mod.logger, "warning") as warn:
            _reaper_with(api)._sweep_undispatched_executions()
        assert warn.called
