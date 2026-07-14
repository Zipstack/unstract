"""Unit tests for the PG finalization-strand fixes.

- L2: ``_update_execution_status_unified`` re-raises on the PG path (so the failed
  finalization vt-redelivers / poison-drops) but swallows on the Celery path.
- L3: ``_backoff_with_jitter`` spreads retries across [base/2, base] (equal jitter)
  so concurrent workers don't retry in synchronized waves.
"""

from unittest.mock import MagicMock, patch

import pytest

_JITTER_FLAG = "shared.clients.base_client.check_feature_flag_status"


class TestBackoffJitter:
    def test_flag_off_returns_exact_base(self):
        # Celery flow (pg_queue_enabled off): exact exponential backoff, no jitter.
        from shared.clients.base_client import _backoff_with_jitter

        with patch(_JITTER_FLAG, return_value=False):
            assert _backoff_with_jitter(1.0, 2) == pytest.approx(4.0)

    def test_flipt_error_fails_closed_to_no_jitter(self):
        from shared.clients.base_client import _backoff_with_jitter

        with patch(_JITTER_FLAG, side_effect=RuntimeError("flipt down")):
            assert _backoff_with_jitter(1.0, 2) == pytest.approx(4.0)

    def test_within_equal_jitter_band_when_flag_on(self):
        from shared.clients.base_client import _backoff_with_jitter

        # base = backoff_factor(1.0) * 2**attempt(2) = 4.0 → equal jitter [2.0, 4.0]
        with patch(_JITTER_FLAG, return_value=True):
            for _ in range(500):
                assert 2.0 <= _backoff_with_jitter(1.0, 2) <= 4.0

    def test_zero_base_returns_zero(self):
        from shared.clients.base_client import _backoff_with_jitter

        with patch(_JITTER_FLAG, return_value=True):
            assert _backoff_with_jitter(0.0, 3) == pytest.approx(0.0)

    def test_is_not_constant_when_flag_on(self):
        from shared.clients.base_client import _backoff_with_jitter

        # De-correlation: repeated calls must NOT all land on the same value
        # (that synchronized schedule is exactly the thundering herd we fix).
        with patch(_JITTER_FLAG, return_value=True):
            assert len({_backoff_with_jitter(1.0, 3) for _ in range(64)}) > 1


class TestPGFinalizationReraise:
    AGG = {"total_files": 1, "successful_files": 1, "failed_files": 0}

    def _run(self, is_pg: bool, fail: bool):
        from callback.tasks import _update_execution_status_unified

        api = MagicMock()
        if fail:
            api.update_workflow_execution_status.side_effect = RuntimeError("boom")
        return (
            api,
            lambda: _update_execution_status_unified(
                api_client=api,
                execution_id="exec-1",
                final_status="COMPLETED",
                aggregated_results=self.AGG,
                organization_id="org-1",
                is_pg=is_pg,
            ),
        )

    def test_pg_reraises_on_write_failure(self):
        # The whole point: a failed finalization on PG must propagate so the
        # message vt-redelivers instead of stranding the execution.
        _api, call = self._run(is_pg=True, fail=True)
        with pytest.raises(RuntimeError):
            call()

    def test_celery_swallows_on_write_failure(self):
        # Celery behavior is unchanged — swallow and return the error dict.
        _api, call = self._run(is_pg=False, fail=True)
        result = call()
        assert result["status"] == "failed"

    def test_success_path_returns_completed_for_pg(self):
        api, call = self._run(is_pg=True, fail=False)
        result = call()
        assert result["status"] == "completed"
        api.update_workflow_execution_status.assert_called_once()


class TestRecoverStuckClientResponseShape:
    """The recovery endpoint returns a FLAT body (no {"data": ...} envelope). The
    client must surface it as ``APIResponse.data`` so the reaper's observability
    block can read the counters — convert_dict_response() would zero them all."""

    def _client(self, post_return):
        from shared.clients.execution_client import ExecutionAPIClient

        client = ExecutionAPIClient.__new__(ExecutionAPIClient)
        client._build_url = MagicMock(return_value="/recover/")
        client.post = MagicMock(return_value=post_return)
        return client

    def test_flat_body_surfaced_as_data(self):
        body = {"recovered": 3, "skipped": 2, "scanned": 5, "failed": 0}
        resp = self._client(body).recover_stuck_pg_executions(stuck_seconds=9000)
        assert resp.data == body
        assert resp.data.get("recovered") == 3  # reaper reads a real count, not 0

    def test_non_dict_body_yields_empty_data(self):
        # A malformed (non-dict) body → empty data → the reaper's loud-guard fires.
        resp = self._client(None).recover_stuck_pg_executions()
        assert not resp.data
