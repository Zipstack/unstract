"""The active-org prefilter can actually use we_created_at_idx (UN-3974, AC-3).

AC-3 is worded as a production observation — "no longer appears in the top 10 by total
execution time in Query Insights" — and that half can only be read off production. The
half that is answerable here is the one underneath it: the prefilter bounds nothing but
`created_at`, and the index exists to serve exactly that shape.

What this pins is the pairing. `workflow_manager/workflow_v2/tests/test_we_created_at_idx.py`
proves the index is declared and built safely; this proves the query still looks like
something it can serve. Either half can drift without the other noticing — someone
narrowing the prefilter to lead with a different column leaves the index built, valid,
and dead.

Rows are inserted in ascending `created_at` order so the heap matches production, where
executions are appended as they happen. With them scattered the planner reads the whole
composite (workflow_id, created_at DESC) index instead, which is an artefact of the
fixture rather than anything about the query.

DB-bound, so conftest marks it integration.
"""

from __future__ import annotations


from account_v2.models import Organization
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from dashboard_metrics.tasks import AggregationTier, _run_aggregation

INDEX_NAME = "we_created_at_idx"
_ROWS = 12000
_SPAN_DAYS = 255


class TestThePrefilterCanUseTheIndex(TestCase):
    """Production ratios rather than production size: ~2.7% of rows in the 7-day window
    is what decides whether the planner reaches for an index or scans.
    """

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            organization_id="prefilter-org", name="prefilter", display_name="Prefilter"
        )
        self.workflow = Workflow.objects.create(
            workflow_name="prefilter-wf", organization=self.org
        )
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflow_execution (
                    id, created_at, modified_at, workflow_id, execution_mode,
                    execution_method, execution_type, execution_log_id, status,
                    error_message, attempts, execution_time, result_acknowledged,
                    total_files)
                SELECT gen_random_uuid(), ts, ts, %s, 'INSTANT', 'DIRECT', 'COMPLETE',
                       '', 'COMPLETED', '', 0, 1.0, false, 1
                FROM generate_series(1, %s) g
                CROSS JOIN LATERAL (
                    SELECT now() - (%s - (g::float / %s) * %s) * interval '1 day'
                ) AS t(ts)
                """,
                [self.workflow.id, _ROWS, _SPAN_DAYS, _ROWS, _SPAN_DAYS],
            )
            cur.execute("ANALYZE workflow_execution")

    def _prefilter_sql(self) -> str:
        """The real query, taken from the task rather than rewritten here.

        A hand-copied queryset would keep passing after the prefilter changed, which is
        the one thing this test is for.
        """
        with CaptureQueriesContext(connection) as ctx:
            _run_aggregation(AggregationTier.HOURLY)
        candidates = [
            q["sql"]
            for q in ctx.captured_queries
            if "workflow_execution" in q["sql"]
            and "DISTINCT" in q["sql"].upper()
            and "created_at" in q["sql"]
        ]
        assert candidates, "the aggregation issued no active-org prefilter query"
        return str(candidates[0])

    def test_the_window_is_the_selectivity_the_index_is_for(self) -> None:
        """If the prefilter ever widened to most of the table, an index on created_at
        would stop being the right answer — the planner would scan regardless.
        """
        with connection.cursor() as cur:
            cur.execute(
                "SELECT count(*) FILTER (WHERE created_at >= now() - interval '7 days')"
                "::float / count(*) FROM workflow_execution"
            )
            share = cur.fetchone()[0]
        assert 0 < share < 0.10

    def test_the_planner_reaches_for_the_index(self) -> None:
        """The whole point of 2a. An index that exists but is never chosen costs on
        every insert and buys nothing.
        """
        with connection.cursor() as cur:
            cur.execute("EXPLAIN " + self._prefilter_sql())
            plan = "\n".join(row[0] for row in cur.fetchall())
        assert INDEX_NAME in plan, f"expected {INDEX_NAME} in:\n{plan}"

    def test_the_prefilter_does_not_scan_the_executions_table(self) -> None:
        """The regression the index is meant to remove."""
        with connection.cursor() as cur:
            cur.execute("EXPLAIN " + self._prefilter_sql())
            plan = "\n".join(row[0] for row in cur.fetchall())
        assert "Seq Scan on workflow_execution" not in plan, plan
