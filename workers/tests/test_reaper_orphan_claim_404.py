"""Reaper orphan-claim 404 handling (UN-3719).

A pg_orchestration_claim whose workflow_execution row was deleted (retention /
cleanup) is a pure orphan. The status read returns a deterministic 404 *with the
backend's own marker*, so the reaper GC's the claim instead of retrying it forever.
A transient failure (5xx / transport) — or any 404 that isn't the backend saying
"WorkflowExecution not found" (proxy / gateway / org-scope) — still raises → the
claim is retained.
"""

from unittest.mock import MagicMock

import pytest

_MARKER = 'Client error: 404 Not Found: {"error": "WorkflowExecution not found"}'


def _resp(success, status=None, status_code=None, error=""):
    r = MagicMock()
    r.success = success
    r.status = status
    r.status_code = status_code
    r.error = error
    return r


def _api(response):
    api = MagicMock()
    api.get_workflow_execution.return_value = response
    return api


class TestExecutionStatusGoneDetection:
    def test_success_returns_status(self):
        from queue_backend.pg_queue.reaper import _execution_status

        api = _api(_resp(True, status="COMPLETED"))
        assert _execution_status(api, "exec-1", "org-1") == "COMPLETED"

    def test_404_with_marker_returns_gone(self):
        from queue_backend.pg_queue.reaper import _EXECUTION_GONE, _execution_status

        api = _api(_resp(False, status_code=404, error=_MARKER))
        assert _execution_status(api, "exec-1", "org-1") is _EXECUTION_GONE

    def test_404_without_marker_raises(self):
        # A proxy / gateway / deploy-skew 404 (no app marker) must NOT be "gone" —
        # otherwise a bad deploy 404s every read and GC's every claim at once.
        from queue_backend.pg_queue.reaper import _execution_status

        api = _api(_resp(False, status_code=404, error="Client error: 404: <html>nginx</html>"))
        with pytest.raises(RuntimeError):
            _execution_status(api, "exec-1", "org-1")

    def test_403_raises_and_is_not_gone(self):
        # Pins "only 404 is GONE": a non-404 4xx (auth blip / conflict) must raise, so
        # loosening the check to >=400 would fail here instead of GC-ing live claims.
        from queue_backend.pg_queue.reaper import _execution_status

        api = _api(_resp(False, status_code=403, error="Client error: 403 Forbidden"))
        with pytest.raises(RuntimeError):
            _execution_status(api, "exec-1", "org-1")

    def test_500_raises_transient(self):
        from queue_backend.pg_queue.reaper import _execution_status

        api = _api(_resp(False, status_code=500, error="Server error: 500"))
        with pytest.raises(RuntimeError):
            _execution_status(api, "exec-1", "org-1")

    def test_transport_failure_without_status_code_raises(self):
        from queue_backend.pg_queue.reaper import _execution_status

        api = _api(_resp(False, status_code=None, error="Connection reset"))
        with pytest.raises(RuntimeError):
            _execution_status(api, "exec-1", "org-1")


class TestRecoverOneClaimGcsDeletedExecution:
    def test_gone_execution_is_gcd(self, monkeypatch):
        import queue_backend.pg_queue.reaper as r

        monkeypatch.setattr(r, "_execution_status", lambda *a, **k: r._EXECUTION_GONE)
        monkeypatch.setattr(r, "_delete_orphan_claim", lambda *a, **k: 1)  # 1 row gone
        outcome = r._recover_one_claim(
            MagicMock(), MagicMock(), "exec-1", "org-1", 9000
        )
        assert outcome == r._CLAIM_GC

    def test_gone_but_reclaimed_in_race_leaves_it(self, monkeypatch):
        # A concurrent release+re-claim replaced the row → 0-row delete → leave it.
        import queue_backend.pg_queue.reaper as r

        monkeypatch.setattr(r, "_execution_status", lambda *a, **k: r._EXECUTION_GONE)
        monkeypatch.setattr(r, "_delete_orphan_claim", lambda *a, **k: 0)  # race lost
        outcome = r._recover_one_claim(
            MagicMock(), MagicMock(), "exec-1", "org-1", 9000
        )
        assert outcome is None


class TestApiRequestErrorStatusCode:
    def test_carries_status_code(self):
        from shared.clients.base_client import APIRequestError

        assert APIRequestError("m", status_code=404).status_code == 404

    def test_defaults_to_none(self):
        from shared.clients.base_client import APIRequestError

        assert APIRequestError("m").status_code is None


class TestStatusCodePropagationChain:
    """The real chain the reaper depends on, end to end: base_client raises
    APIRequestError(status_code=…) → get_workflow_execution catches → ExecutionResponse
    carries .status_code + .error. The mock-based reaper tests can't catch a rename in
    this chain; this does."""

    def _client(self, exc):
        from shared.clients.execution_client import ExecutionAPIClient

        client = ExecutionAPIClient.__new__(ExecutionAPIClient)
        client._build_url = MagicMock(return_value="/we/exec-1/")
        client.get = MagicMock(side_effect=exc)
        return client

    def test_404_propagates_status_code_and_marker(self):
        from shared.clients.base_client import APIRequestError

        resp = self._client(APIRequestError(_MARKER, status_code=404)).get_workflow_execution(
            "exec-1", organization_id="org-1"
        )
        assert resp.success is False
        assert resp.status_code == 404
        assert "WorkflowExecution not found" in (resp.error or "")

    def test_500_propagates_status_code(self):
        from shared.clients.base_client import APIRequestError

        resp = self._client(
            APIRequestError("Server error: 500", status_code=500)
        ).get_workflow_execution("exec-1", organization_id="org-1")
        assert resp.success is False
        assert resp.status_code == 500
