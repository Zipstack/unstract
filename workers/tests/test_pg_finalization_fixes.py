"""Unit tests for the PG finalization-strand fixes.

- L2: ``_update_execution_status_unified`` re-raises on the PG path (so the failed
  finalization vt-redelivers / poison-drops) but swallows on the Celery path.
- L3: ``_backoff_with_jitter`` spreads retries across [base/2, base] (equal jitter)
  so concurrent workers don't retry in synchronized waves.
"""

from unittest.mock import MagicMock

import pytest


class TestBackoffJitter:
    def test_within_equal_jitter_band(self):
        from shared.clients.base_client import _backoff_with_jitter

        # base = backoff_factor(1.0) * 2**attempt(2) = 4.0 → equal jitter [2.0, 4.0]
        for _ in range(500):
            assert 2.0 <= _backoff_with_jitter(1.0, 2) <= 4.0

    def test_zero_base_returns_zero(self):
        from shared.clients.base_client import _backoff_with_jitter

        assert _backoff_with_jitter(0.0, 3) == 0.0

    def test_is_not_constant(self):
        from shared.clients.base_client import _backoff_with_jitter

        # De-correlation: repeated calls must NOT all land on the same value
        # (that synchronized schedule is exactly the thundering herd we fix).
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
