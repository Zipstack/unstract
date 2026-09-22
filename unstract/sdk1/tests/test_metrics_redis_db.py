"""Which Redis database the sdk1 metrics keys land on (UN-4123).

This was the last place in the codebase that chose a database in code rather than
in configuration, which is what blocked single-database endpoints: Azure Managed
Redis, Redis Enterprise and every cluster-mode service offer db 0 only.
"""

import pytest
from unstract.sdk1.utils.metrics_mixin import MetricsMixin, _metrics_redis_db


class TestMetricsRedisDb:
    def test_defaults_to_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The value that was hardcoded, so an unset var changes nothing."""
        monkeypatch.delenv("METRICS_REDIS_DB", raising=False)
        assert _metrics_redis_db() == 1

    def test_env_selects_the_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("METRICS_REDIS_DB", "0")
        assert _metrics_redis_db() == 0

    @pytest.mark.parametrize("raw", ["", "   "])
    def test_blank_means_unset(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        """A declared-but-empty variable is this repo's convention for "default".

        int("") used to raise inside __init__'s try/except, so every LLM timing
        metric went silently missing platform-wide — once per instrumented call,
        behind a log line that named Redis rather than this variable.
        """
        monkeypatch.setenv("METRICS_REDIS_DB", raw)
        assert _metrics_redis_db() == 1

    @pytest.mark.parametrize("raw", ["zero", "1.5"])
    def test_unparseable_falls_back_rather_than_losing_every_metric(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """And the warning names the variable, so it is not read as a Redis outage."""
        monkeypatch.setenv("METRICS_REDIS_DB", raw)
        assert _metrics_redis_db() == 1
        assert "METRICS_REDIS_DB" in caplog.text

    def test_metrics_stay_enabled_through_a_bad_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("METRICS_REDIS_DB", "zero")
        metrics = MetricsMixin(run_id="run-1")
        assert metrics.redis_key.startswith("metrics:run-1:")
