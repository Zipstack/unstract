"""Metric groups for the platform ``/metrics`` endpoint.

A group is one unit of refresh: ``fetch`` reads the database and returns a
JSON-safe snapshot, ``families`` turns a snapshot into Prometheus metric
families. The split is what lets the exporter cache a group's snapshot in Redis
(see ``cache.py``) and render it on any backend pod without touching the DB.

Every group zero-fills its known label values, so a drained queue or an idle
status reads 0 instead of disappearing from the scrape.

Adding a group: subclass :class:`MetricGroup` and append an instance to
:data:`METRIC_GROUPS`. The endpoint, caching and failure accounting pick it up
without further changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Count, DurationField, ExpressionWrapper, Min, Q
from django.db.models.functions import Now
from django.utils import timezone

from unstract.core.data_models import ExecutionStatus, QueueMessageState

if TYPE_CHECKING:
    from prometheus_client.core import Metric

Snapshot = dict[str, Any]

_ACTIVE_STATUSES = (ExecutionStatus.PENDING.value, ExecutionStatus.EXECUTING.value)
# Sorted so the series order in the scrape is stable.
_TERMINAL_STATUSES = tuple(sorted(ExecutionStatus.terminal_values()))
_QUEUE_STATES = tuple(state.value for state in QueueMessageState)


class MetricGroup(ABC):
    """One independently cached and refreshed set of metrics."""

    #: Label value for this group on the exporter-health metrics, and the
    #: suffix of its Redis cache / lock keys.
    name: str

    def fetch(self) -> Snapshot:
        """Read a fresh snapshot, bounded by the configured statement timeout.

        ``SET LOCAL`` scopes the timeout to this transaction, so a slow group
        is cancelled by Postgres instead of holding a scrape (and the group's
        refresh lock) open, and nothing leaks onto the pooled connection.
        """
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "SET LOCAL statement_timeout = %s",
                [int(settings.PLATFORM_METRICS_QUERY_TIMEOUT_MS)],
            )
            return self.query()

    @abstractmethod
    def query(self) -> Snapshot:
        """Run the group's queries. Must return JSON-serialisable data."""

    @abstractmethod
    def families(self, snapshot: Snapshot) -> Iterable[Metric]:
        """Build the group's metric families from a snapshot."""


class QueueMetricGroup(MetricGroup):
    """``pg_queue_message`` depth by state and oldest-message age, per queue.

    Same population as the reaper's ``pg_queue_depth`` /
    ``pg_queue_oldest_message_age_seconds`` (``refresh_queue_gauges`` in
    ``workers/queue_backend/pg_queue/reaper.py``): every row counts, and the age
    is ``now() - min(enqueued_at)`` across all states. The per-state counts sum
    to the reaper's depth; this group only adds the split.

    One aggregate over the table, like the reaper's. The table holds only
    undelivered and in-flight messages (acked rows are deleted), so it stays
    small whatever the platform's history.
    """

    name = "queues"

    def query(self) -> Snapshot:
        from pg_queue.models import PgQueueMessage

        rows = (
            PgQueueMessage.objects.values("queue_name", "state")
            .annotate(
                messages=Count("msg_id"),
                oldest_age=ExpressionWrapper(
                    Now() - Min("enqueued_at"), output_field=DurationField()
                ),
            )
            .order_by()
        )
        queues: dict[str, dict[str, Any]] = {}
        for row in rows:
            entry = queues.setdefault(row["queue_name"], {"states": {}, "oldest": 0.0})
            entry["states"][row["state"]] = row["messages"]
            age = row["oldest_age"].total_seconds() if row["oldest_age"] else 0.0
            entry["oldest"] = max(entry["oldest"], max(age, 0.0))
        return {"queues": queues}

    def families(self, snapshot: Snapshot) -> Iterable[Metric]:
        from prometheus_client.core import GaugeMetricFamily

        observed: dict[str, dict[str, Any]] = snapshot["queues"]
        names = sorted(set(settings.PLATFORM_METRICS_QUEUES) | set(observed))
        messages = GaugeMetricFamily(
            "unstract_queue_messages",
            "Messages in pg_queue_message by queue and claim state (ready = "
            "waiting, claimed = held by a consumer, scheduled = delayed until "
            "available_at)",
            labels=["queue", "state"],
        )
        oldest = GaugeMetricFamily(
            "unstract_queue_oldest_message_age_seconds",
            "Age of the oldest message in the queue, any state (0 when empty)",
            labels=["queue"],
        )
        for queue in names:
            entry = observed.get(queue, {"states": {}, "oldest": 0.0})
            for state in _QUEUE_STATES:
                messages.add_metric([queue, state], entry["states"].get(state, 0))
            oldest.add_metric([queue], entry["oldest"])
        return [messages, oldest]


class ExecutionMetricGroup(MetricGroup):
    """``workflow_execution`` counts: active now, and terminal within a window.

    Both queries are index-bounded so they never scan the whole history:

    * active (``PENDING`` / ``EXECUTING``) is implied by the predicate of the
      partial ``we_active_by_workflow_idx``, so it costs O(active executions);
    * recent terminal is bounded by ``created_at`` (``we_created_at_idx``) to
      ``PLATFORM_METRICS_RECENT_LOOKBACK_SECONDS``, then filtered on
      ``modified_at`` — the time the row last changed, i.e. when it went
      terminal. ``modified_at`` is deliberately not indexed (it is rewritten on
      every status update), so an execution that ran longer than the lookback
      before finishing is not counted. The default lookback (24h) is far above
      any normal run.
    """

    name = "executions"

    def query(self) -> Snapshot:
        from workflow_manager.workflow_v2.models.execution import WorkflowExecution

        now = timezone.now()
        window = timedelta(seconds=int(settings.PLATFORM_METRICS_RECENT_WINDOW_SECONDS))
        lookback = timedelta(
            seconds=int(settings.PLATFORM_METRICS_RECENT_LOOKBACK_SECONDS)
        )
        active = (
            WorkflowExecution.objects.filter(status__in=_ACTIVE_STATUSES)
            .values("status")
            .annotate(n=Count("id"))
            .order_by()
        )
        recent = (
            WorkflowExecution.objects.filter(
                status__in=_TERMINAL_STATUSES,
                created_at__gte=now - max(lookback, window),
                modified_at__gte=now - window,
            )
            .values("status")
            .annotate(n=Count("id"))
            .order_by()
        )
        return {
            "active": {row["status"]: row["n"] for row in active},
            "recent": {row["status"]: row["n"] for row in recent},
        }

    def families(self, snapshot: Snapshot) -> Iterable[Metric]:
        from prometheus_client.core import GaugeMetricFamily

        active = GaugeMetricFamily(
            "unstract_workflow_executions",
            "Workflow executions currently in a non-terminal status",
            labels=["status"],
        )
        for status in _ACTIVE_STATUSES:
            active.add_metric([status.lower()], snapshot["active"].get(status, 0))
        recent = GaugeMetricFamily(
            "unstract_workflow_executions_recent",
            "Workflow executions that reached a terminal status within the "
            "recent window (PLATFORM_METRICS_RECENT_WINDOW_SECONDS, default 1h)",
            labels=["status"],
        )
        for status in _TERMINAL_STATUSES:
            recent.add_metric([status.lower()], snapshot["recent"].get(status, 0))
        return [active, recent]


class BatchMetricGroup(MetricGroup):
    """``pg_barrier_state`` fan-outs: in progress, and stuck.

    Matches the reaper's ``pg_barrier_live`` / ``pg_barrier_stranded``: in
    progress is ``remaining > 0``; stuck is the reaper's stranded predicate
    (no progress for the stuck timeout, or past ``expires_at``) — what its next
    recovery pass would pick up. The timeout comes from the same
    ``WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS`` the reaper reads. One row per
    in-flight execution, so the table is small.
    """

    name = "batches"

    def query(self) -> Snapshot:
        from pg_queue.models import PgBarrierState

        stuck_before = Now() - timedelta(
            seconds=int(settings.PLATFORM_METRICS_BATCH_STUCK_TIMEOUT_SECONDS)
        )
        counts = PgBarrierState.objects.aggregate(
            in_progress=Count("execution_id", filter=Q(remaining__gt=0)),
            stuck=Count(
                "execution_id",
                filter=Q(last_progress_at__lt=stuck_before) | Q(expires_at__lt=Now()),
            ),
        )
        return {"in_progress": counts["in_progress"], "stuck": counts["stuck"]}

    def families(self, snapshot: Snapshot) -> Iterable[Metric]:
        from prometheus_client.core import GaugeMetricFamily

        return [
            GaugeMetricFamily(
                "unstract_batches_in_progress",
                "In-flight file-batch fan-outs (pg_barrier_state rows with "
                "remaining > 0)",
                value=snapshot["in_progress"],
            ),
            GaugeMetricFamily(
                "unstract_batches_stuck",
                "Fan-outs past the stuck timeout or their expiry: what the "
                "reaper's next recovery pass picks up",
                value=snapshot["stuck"],
            ),
        ]


#: The groups the endpoint exports, in scrape order.
METRIC_GROUPS: tuple[MetricGroup, ...] = (
    QueueMetricGroup(),
    ExecutionMetricGroup(),
    BatchMetricGroup(),
)
