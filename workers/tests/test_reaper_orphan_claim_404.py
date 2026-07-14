"""Reaper orphan-claim 404 handling (UN-3719).

A pg_orchestration_claim whose workflow_execution row was deleted (retention /
cleanup) is a pure orphan. The status read now returns a deterministic 404, so the
reaper GC's the claim instead of retrying it forever (which left it poisoning every
sweep). A *transient* failure (5xx / transport) still raises → the claim is retained.
"""

from unittest.mock import MagicMock

import pytest


def _resp(success, status=None, status_code=None):
    r = MagicMock()
    r.success = success
    r.status = status
    r.status_code = status_code
    return r


class TestExecutionStatusGoneDetection:
    def _call(self, response):
        from queue_backend.pg_queue.reaper import _execution_status

        api = MagicMock()
        api.get_workflow_execution.return_value = response
        return _execution_status(api, "exec-1", "org-1")

    def test_success_returns_status(self):
        assert self._call(_resp(True, status="COMPLETED")) == "COMPLETED"

    def test_404_returns_gone_sentinel(self):
        from queue_backend.pg_queue.reaper import _EXECUTION_GONE

        assert self._call(_resp(False, status_code=404)) is _EXECUTION_GONE

    def test_500_raises_transient(self):
        # A server error is transient — raise so the claim is retained, never
        # terminalized on an unconfirmed read.
        with pytest.raises(RuntimeError):
            self._call(_resp(False, status_code=500))

    def test_transport_failure_without_status_code_raises(self):
        # No HTTP status (connection reset etc.) → transient → retain.
        with pytest.raises(RuntimeError):
            self._call(_resp(False, status_code=None))


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
