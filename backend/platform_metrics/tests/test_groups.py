"""Metric groups: names, labels and zero-filling (DB-free)."""

from django.test import override_settings
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families

from platform_metrics.groups import (
    BatchMetricGroup,
    ExecutionMetricGroup,
    QueueMetricGroup,
)


def _render(group, snapshot):
    class _Collector:
        def collect(self):
            return group.families(snapshot)

    registry = CollectorRegistry()
    registry.register(_Collector())
    text = generate_latest(registry).decode()
    samples = {}
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            samples[(sample.name, tuple(sorted(sample.labels.items())))] = sample.value
    return samples


@override_settings(PLATFORM_METRICS_QUEUES=["celery", "file_processing"])
def test_queue_series_are_zero_filled_for_known_queues_and_states():
    samples = _render(
        QueueMetricGroup(),
        {"queues": {"celery": {"states": {"ready": 4, "claimed": 2}, "oldest": 12.5}}},
    )

    def messages(queue, state):
        return samples[
            ("unstract_queue_messages", (("queue", queue), ("state", state)))
        ]

    assert messages("celery", "ready") == 4
    assert messages("celery", "claimed") == 2
    assert messages("celery", "scheduled") == 0
    for state in ("ready", "claimed", "scheduled"):
        assert messages("file_processing", state) == 0
    age = "unstract_queue_oldest_message_age_seconds"
    assert samples[(age, (("queue", "celery"),))] == 12.5
    assert samples[(age, (("queue", "file_processing"),))] == 0


@override_settings(PLATFORM_METRICS_QUEUES=["celery"])
def test_queue_not_in_the_known_list_is_still_reported():
    samples = _render(
        QueueMetricGroup(),
        {"queues": {"custom_queue": {"states": {"scheduled": 1}, "oldest": 3.0}}},
    )

    queues = {
        dict(labels)["queue"]
        for name, labels in samples
        if name == "unstract_queue_messages"
    }
    assert queues == {"celery", "custom_queue"}


def test_execution_series_are_zero_filled_with_lowercase_status():
    samples = _render(
        ExecutionMetricGroup(),
        {"active": {"PENDING": 3}, "recent": {"COMPLETED": 10, "ERROR": 1}},
    )

    assert samples == {
        ("unstract_workflow_executions", (("status", "pending"),)): 3,
        ("unstract_workflow_executions", (("status", "executing"),)): 0,
        ("unstract_workflow_executions_recent", (("status", "completed"),)): 10,
        ("unstract_workflow_executions_recent", (("status", "error"),)): 1,
        ("unstract_workflow_executions_recent", (("status", "stopped"),)): 0,
    }


def test_batch_series():
    samples = _render(BatchMetricGroup(), {"in_progress": 5, "stuck": 1})

    assert samples == {
        ("unstract_batches_in_progress", ()): 5,
        ("unstract_batches_stuck", ()): 1,
    }


def test_group_names_are_unique():
    from platform_metrics.groups import METRIC_GROUPS

    names = [group.name for group in METRIC_GROUPS]
    assert sorted(names) == ["batches", "executions", "queues"]
