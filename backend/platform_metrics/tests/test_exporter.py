"""Exporter: exposition format, exporter-health metrics, failure isolation."""

import pytest
from django.test import override_settings
from prometheus_client.parser import text_string_to_metric_families

from platform_metrics.cache import FailureCounter, SnapshotCache
from platform_metrics.exporter import PlatformMetricsExporter
from platform_metrics.tests.fakes import Clock, FakeRedis, StubGroup


@pytest.fixture(autouse=True)
def _ttl():
    with override_settings(PLATFORM_METRICS_CACHE_TTL_SECONDS=15):
        yield


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def redis():
    return FakeRedis()


def _exporter(groups, redis, clock):
    return PlatformMetricsExporter(
        groups=groups,
        cache=SnapshotCache(client_factory=lambda: redis, clock=clock),
        failures=FailureCounter(client_factory=lambda: redis),
    )


def _samples(exporter):
    out = {}
    for family in text_string_to_metric_families(exporter.render().decode()):
        for sample in family.samples:
            out[(sample.name, tuple(sorted(sample.labels.items())))] = sample.value
    return out


def test_renders_every_group_with_health_metrics(redis, clock):
    exporter = _exporter([StubGroup("a", 1), StubGroup("b", 2)], redis, clock)

    samples = _samples(exporter)

    assert samples[("stub_a", ())] == 1
    assert samples[("stub_b", ())] == 2
    refreshed = "unstract_metrics_last_successful_refresh_timestamp"
    assert samples[(refreshed, (("group", "a"),))] == clock.now
    assert samples[(refreshed, (("group", "b"),))] == clock.now
    failures = "unstract_metrics_refresh_failures_total"
    assert samples[(failures, (("group", "a"),))] == 0
    assert samples[(failures, (("group", "b"),))] == 0


def test_failing_group_does_not_affect_the_others(redis, clock):
    healthy, broken = StubGroup("a", 1), StubGroup("b", 2)
    broken.error = RuntimeError("db down")
    exporter = _exporter([healthy, broken], redis, clock)

    samples = _samples(exporter)

    assert samples[("stub_a", ())] == 1
    assert ("stub_b", ()) not in samples, "nothing cached yet, so nothing to serve"
    failures = "unstract_metrics_refresh_failures_total"
    assert samples[(failures, (("group", "b"),))] == 1
    assert samples[(failures, (("group", "a"),))] == 0


def test_failing_group_serves_its_last_values(redis, clock):
    group = StubGroup("a", 1)
    exporter = _exporter([group], redis, clock)
    _samples(exporter)
    first_refresh = clock.now

    clock.now += 60
    group.value = 99
    group.error = RuntimeError("db down")
    samples = _samples(exporter)

    assert samples[("stub_a", ())] == 1
    refreshed = "unstract_metrics_last_successful_refresh_timestamp"
    assert samples[(refreshed, (("group", "a"),))] == first_refresh
    assert samples[("unstract_metrics_refresh_failures_total", (("group", "a"),))] == 1


def test_unexpected_cache_error_is_counted_not_raised(redis, clock):
    class BrokenCache:
        def resolve(self, group):
            raise ValueError("bug")

    exporter = PlatformMetricsExporter(
        groups=[StubGroup("a")],
        cache=BrokenCache(),
        failures=FailureCounter(client_factory=lambda: redis),
    )

    samples = _samples(exporter)

    assert samples[("unstract_metrics_refresh_failures_total", (("group", "a"),))] == 1


def test_snapshot_that_no_longer_renders_is_dropped_and_counted(redis, clock):
    """E.g. a snapshot an older pod cached in a different shape mid-deploy."""
    redis.data["platform_metrics:v1:data:a"] = (
        '{"data": {"unexpected": 1}, "refreshed_at": %s}' % clock.now
    )
    exporter = _exporter([StubGroup("a"), StubGroup("b", 2)], redis, clock)

    samples = _samples(exporter)

    assert ("stub_a", ()) not in samples
    assert samples[("stub_b", ())] == 2
    assert samples[("unstract_metrics_refresh_failures_total", (("group", "a"),))] == 1


FAILURES = "unstract_metrics_refresh_failures_total"


def test_failure_total_is_shared_across_processes(redis, clock):
    """Every gunicorn worker reports the same total, so it never jumps back."""
    broken = StubGroup("a")
    broken.error = RuntimeError("db down")
    worker_1 = _exporter([broken], redis, clock)
    worker_2 = _exporter([broken], redis, clock)

    _samples(worker_1)
    clock.now += 60
    samples_2 = _samples(worker_2)
    samples_1 = _samples(worker_1)

    assert samples_2[(FAILURES, (("group", "a"),))] == 2
    assert samples_1[(FAILURES, (("group", "a"),))] == 3


def test_failures_while_redis_is_down_are_kept_and_flushed_later(redis, clock):
    group = StubGroup("a")
    exporter = _exporter([group], redis, clock)
    redis.down = True

    samples = _samples(exporter)

    assert (FAILURES, (("group", "a"),)) not in samples, (
        "absent, not this process's partial count"
    )
    assert samples[("unstract_metrics_cache_up", ())] == 0
    redis.down = False
    clock.now += 60
    samples = _samples(exporter)
    assert samples[(FAILURES, (("group", "a"),))] == 1
    assert samples[("unstract_metrics_cache_up", ())] == 1


def test_unreadable_failure_total_does_not_break_the_scrape(redis, clock):
    redis.hashes["platform_metrics:v1:refresh_failures"] = {"a": "1.5", "b": 2}
    exporter = _exporter([StubGroup("a"), StubGroup("b")], redis, clock)

    samples = _samples(exporter)

    assert samples[(FAILURES, (("group", "a"),))] == 0
    assert samples[(FAILURES, (("group", "b"),))] == 2


def test_output_is_prometheus_text_with_help_and_type(redis, clock):
    text = _exporter([StubGroup("a")], redis, clock).render().decode()

    assert "# HELP unstract_metrics_refresh_failures_total" in text
    assert "# TYPE unstract_metrics_refresh_failures_total counter" in text
    assert "# TYPE unstract_metrics_last_successful_refresh_timestamp gauge" in text
