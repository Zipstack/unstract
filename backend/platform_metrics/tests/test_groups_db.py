"""Metric group queries against a real database (integration tier).

These pin that each group counts what its docstring says it counts, including
the edges that matter for consistency with the PG reaper: the stuck predicate,
the recent-window bounds, and that queue state counts add up to the depth.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

from unstract.core.data_models import ExecutionStatus

pytestmark = pytest.mark.django_db


def _message(queue, state, enqueued_ago=timedelta(0)):
    from pg_queue.models import PgQueueMessage

    return PgQueueMessage.objects.create(
        queue_name=queue,
        message={},
        state=state,
        enqueued_at=timezone.now() - enqueued_ago,
    )


def _execution(status, created_ago=timedelta(minutes=5), ran_for=None):
    """An execution created ``created_ago``, terminal after ``ran_for``.

    ``modified_at`` is set to now on purpose: later writes (an API result being
    acknowledged, for one) bump it, so the group must not read it as the
    completion time.
    """
    from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

    ex = WorkflowExecution.objects.create(
        id=uuid.uuid4(),
        workflow=Workflow.objects.create(workflow_name=f"wf-{uuid.uuid4().hex[:8]}"),
        status=status,
    )
    now = timezone.now()
    WorkflowExecution.objects.filter(id=ex.id).update(
        created_at=now - created_ago,
        execution_time=(ran_for or timedelta(0)).total_seconds(),
        modified_at=now,
    )
    return ex


def _barrier(remaining, progress_ago=timedelta(0), expires_in=timedelta(hours=6)):
    from pg_queue.models import PgBarrierState

    now = timezone.now()
    return PgBarrierState.objects.create(
        execution_id=str(uuid.uuid4()),
        remaining=remaining,
        # Before both, so an already-expired row still passes the
        # expires-after-created constraint.
        created_at=now - timedelta(days=1),
        expires_at=now + expires_in,
        last_progress_at=now - progress_ago,
    )


class TestQueueGroup:
    def test_counts_by_queue_and_state_with_oldest_age_across_states(self):
        from platform_metrics.groups import QueueMetricGroup

        _message("celery", "ready", enqueued_ago=timedelta(seconds=30))
        _message("celery", "ready")
        _message("celery", "claimed", enqueued_ago=timedelta(seconds=120))
        _message("scheduler", "scheduled", enqueued_ago=timedelta(seconds=10))

        queues = QueueMetricGroup().fetch()["queues"]

        assert queues["celery"]["states"] == {"ready": 2, "claimed": 1}
        assert queues["celery"]["oldest"] == pytest.approx(120, abs=5)
        assert queues["scheduler"]["states"] == {"scheduled": 1}
        assert queues["scheduler"]["oldest"] == pytest.approx(10, abs=5)

    def test_empty_table(self):
        from platform_metrics.groups import QueueMetricGroup

        assert QueueMetricGroup().fetch() == {"queues": {}}


class TestExecutionGroup:
    @override_settings(
        PLATFORM_METRICS_RECENT_WINDOW_SECONDS=3600,
        PLATFORM_METRICS_RECENT_LOOKBACK_SECONDS=86400,
    )
    def test_active_and_recent_counts(self):
        from platform_metrics.groups import ExecutionMetricGroup

        _execution(ExecutionStatus.PENDING.value)
        _execution(ExecutionStatus.EXECUTING.value)
        _execution(ExecutionStatus.EXECUTING.value)
        # Old execution, but finished recently: counted.
        _execution(
            ExecutionStatus.COMPLETED.value,
            created_ago=timedelta(hours=5),
            ran_for=timedelta(hours=4, minutes=50),
        )
        _execution(ExecutionStatus.ERROR.value)
        # Finished before the window, touched since (e.g. its result was
        # acknowledged just now): not counted.
        _execution(
            ExecutionStatus.COMPLETED.value,
            created_ago=timedelta(hours=3),
            ran_for=timedelta(hours=1),
        )
        # Created before the lookback: outside the scan, by design.
        _execution(
            ExecutionStatus.STOPPED.value,
            created_ago=timedelta(days=2),
            ran_for=timedelta(days=2) - timedelta(minutes=1),
        )

        snapshot = ExecutionMetricGroup().fetch()

        assert snapshot["active"] == {"PENDING": 1, "EXECUTING": 2}
        assert snapshot["recent"] == {"COMPLETED": 1, "ERROR": 1}


class TestBatchGroup:
    @override_settings(PLATFORM_METRICS_BATCH_STUCK_TIMEOUT_SECONDS=600)
    def test_in_progress_and_stuck_match_the_reaper_predicates(self):
        from platform_metrics.groups import BatchMetricGroup

        _barrier(remaining=3)  # live, healthy
        _barrier(remaining=2, progress_ago=timedelta(minutes=20))  # live, stuck
        _barrier(remaining=1, expires_in=timedelta(minutes=-1))  # live, expired
        # remaining == 0 lingerer past the timeout: not live, but stranded —
        # the reaper's recovery pass picks it up, so it counts as stuck.
        _barrier(remaining=0, progress_ago=timedelta(minutes=20))

        assert BatchMetricGroup().fetch() == {"in_progress": 3, "stuck": 3}


def test_fetch_applies_the_statement_timeout():
    """A slow group is cancelled by Postgres rather than holding the scrape."""
    from django.db import OperationalError, connection

    from platform_metrics.groups import MetricGroup

    class Slow(MetricGroup):
        name = "slow"

        def query(self):
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_sleep(2)")
            return {}

        def families(self, snapshot):
            return []

    with override_settings(PLATFORM_METRICS_QUERY_TIMEOUT_MS=100):
        with pytest.raises(OperationalError):
            Slow().fetch()
