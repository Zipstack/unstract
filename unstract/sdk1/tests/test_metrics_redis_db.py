"""Which Redis database the sdk1 metrics keys land on (UN-4123).

This was the last place in the codebase that chose a database in code rather than
in configuration, which is what blocked single-database endpoints: Azure Managed
Redis, Redis Enterprise and every cluster-mode service offer db 0 only.
"""

import pytest
from pytest import MonkeyPatch
from unstract.sdk1.utils.metrics_mixin import MetricsMixin, _metrics_redis_db


class TestMetricsRedisDb:
    def test_defaults_to_one(self, monkeypatch: MonkeyPatch) -> None:
        """The value that was hardcoded, so an unset var changes nothing."""
        monkeypatch.delenv("METRICS_REDIS_DB", raising=False)
        assert _metrics_redis_db() == 1

    def test_env_selects_the_database(self, monkeypatch: MonkeyPatch) -> None:
        monkeypatch.setenv("METRICS_REDIS_DB", "0")
        assert _metrics_redis_db() == 0

    @pytest.mark.parametrize("raw", ["", "zero", "1.5"])
    def test_malformed_value_costs_the_metric_not_the_process(
        self, monkeypatch: MonkeyPatch, raw: str
    ) -> None:
        """A bad value must not kill a tool run.

        The read is per instance, inside __init__'s existing try/except, so the
        client is simply left unset and collect_metrics() reports None — the same
        degradation as an unreachable Redis.
        """
        monkeypatch.setenv("METRICS_REDIS_DB", raw)
        with pytest.raises(ValueError):
            _metrics_redis_db()

        metrics = MetricsMixin(run_id="run-1")
        assert metrics.redis_client is None
        assert metrics.collect_metrics() == {MetricsMixin.TIME_TAKEN_KEY: None}
