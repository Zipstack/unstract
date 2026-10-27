"""Exporter: exposition format, exporter-health metrics, failure isolation."""

import pytest
from django.test import override_settings
from prometheus_client.parser import text_string_to_metric_families

from platform_metrics.cache import SnapshotCache
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

    exporter = PlatformMetricsExporter(groups=[StubGroup("a")], cache=BrokenCache())

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


def test_output_is_prometheus_text_with_help_and_type(redis, clock):
    text = _exporter([StubGroup("a")], redis, clock).render().decode()

    assert "# HELP unstract_metrics_refresh_failures_total" in text
    assert "# TYPE unstract_metrics_refresh_failures_total counter" in text
    assert "# TYPE unstract_metrics_last_successful_refresh_timestamp gauge" in text
