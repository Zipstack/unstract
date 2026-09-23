"""Which Redis database the sdk1 metrics keys land on (UN-4123).

This was the last place in the codebase that chose a database in code rather than
in configuration, which is what blocked single-database endpoints: the
non-clustered tiers of Azure Managed Redis and Redis Enterprise offer db 0 only.
(Cluster mode is a different, unsupported thing — a plain redis.Redis gets MOVED
redirects however many databases the service has.)
"""

import pytest
from unstract.sdk1.utils import metrics_mixin
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
    def test_blank_means_unset(
        self, monkeypatch: pytest.MonkeyPatch, raw: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A declared-but-empty variable is this repo's convention for "default".

        int("") used to raise inside __init__'s try/except, so every LLM timing
        metric went silently missing platform-wide — once per instrumented call,
        behind a log line that named Redis rather than this variable.
        """
        monkeypatch.setenv("METRICS_REDIS_DB", raw)
        assert _metrics_redis_db() == 1
        # Without this the test cannot tell "blank is UNSET" from "blank is
        # unparseable, warn and fall back" — both return 1, but only one of them
        # is the convention, and the other logs on every instrumented call.
        assert "METRICS_REDIS_DB" not in caplog.text

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
        """Enabled means a client was built, on the fallback db, and kept.

        Asserting on ``redis_key`` proved nothing: __init__ assigns it after the
        try/except, so it held whatever happened — including the pre-fix state
        where _metrics_redis_db() raised and redis_client was left None. The
        factory is patched rather than reached, so this neither needs a live
        server nor writes 24h-TTL keys to whatever REDIS_URL the shell happens to
        export.
        """
        monkeypatch.setenv("METRICS_REDIS_DB", "zero")
        calls: list[dict] = []
        sentinel = _FakeRedis()

        def _factory(**kwargs: object) -> "_FakeRedis":
            calls.append(kwargs)
            return sentinel

        monkeypatch.setattr(metrics_mixin, "create_redis_client", _factory)
        metrics = MetricsMixin(run_id="run-1")

        assert calls == [{"db": 1}], "the fallback database must still be used"
        assert metrics.redis_client is sentinel, "the client must be kept, not dropped"
        assert metrics.redis_key.startswith("metrics:run-1:")
        assert sentinel.sets, "set_start_time must have written the start marker"


class _FakeRedis:
    """Just enough of redis.Redis for MetricsMixin.__init__'s set_start_time()."""

    def __init__(self) -> None:
        self.sets: list[tuple] = []

    def set(self, *args: object, **kwargs: object) -> None:
        self.sets.append((args, kwargs))
