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

**Not production evidence.** A few thousand rows in an otherwise-empty table on a
locally-configured Postgres is not the production planner's input: index-vs-seq-scan at
this selectivity is a cost-model output, sensitive to the PG major version,
`random_page_cost`, `effective_cache_size` and parallel workers, none of which are
pinned here. What the plan assertion below rules out is the *regression* — a prefilter
that has to read the executions table whatever the costs say. Whether production picks
the index is measured on production, and belongs to AC-3.

DB-bound, so conftest marks it integration.
"""

from __future__ import annotations

import os

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from account_v2.models import Organization  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import TestCase  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from workflow_manager.workflow_v2.models.workflow import Workflow  # noqa: E402

from dashboard_metrics.tasks import AggregationTier, _run_aggregation  # noqa: E402

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
        # The run issues nine further queries against this table, several of them
        # joining it and filtering created_at. Index 0 is right today only by execution
        # order, which nothing here states — so require the shape to be unambiguous.
        assert candidates, "the aggregation issued no active-org prefilter query"
        assert len(candidates) == 1, (
            f"{len(candidates)} queries match the prefilter shape; the match is no "
            f"longer distinguishing:\n" + "\n\n".join(candidates)
        )
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

    def test_the_index_can_serve_the_prefilter(self) -> None:
        """*Usable*, not *chosen*.

        Whether the planner picks the index on a synthetic table turns on
        random_page_cost, effective_cache_size, the PG major version and how the
        freshly-loaded visibility map looks — none of which this fixture pins, so
        asserting the choice reds the build on a config change with no code change.
        Disabling seqscan asks the question that is actually about the query: can this
        shape be served from the index at all? A prefilter narrowed to lead with a
        different column fails here whatever the cost model says.
        """
        sql = self._prefilter_sql()
        with connection.cursor() as cur:
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute("EXPLAIN " + sql)
            plan = "\n".join(row[0] for row in cur.fetchall())
        assert f"Index Scan using {INDEX_NAME}" in plan or f"Index Only Scan using {INDEX_NAME}" in plan, (
            f"expected {INDEX_NAME} to be usable for the prefilter:\n{plan}"
        )
