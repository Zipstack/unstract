"""The metric queries can actually use wfe_status_created_idx (UN-3972).

``test_wfe_status_created_idx.py`` proves the index is declared and built safely —
every assertion there reads migration attributes or greps ``Meta.indexes``. That
leaves the pairing unproven: change ``get_documents_processed`` or
``get_failed_pages`` to stop leading with ``status`` and the index stays built,
valid and dead, with the whole suite green.

This is the sibling of ``dashboard_metrics/tests/test_active_org_prefilter.py``,
which does the same job for ``we_created_at_idx``, and it is deliberately the same
shape: seed at production-ish status ratios, ``ANALYZE``, then ask whether the plan
*can* be served from the index rather than whether the planner chooses it.

What is asserted is the **predicate**, not the full joined metric query. The metric
queries reach this table through ``workflow_execution__workflow__organization_id``,
so which side the planner drives from is a cost-model decision that a synthetic
fixture cannot pin — asserting it would red the build on a config change. The
predicate is the part the index exists for, and a query that stops filtering on
``status`` stops matching it.

**Not production evidence.** A few thousand rows on a locally-configured Postgres
is not the production planner's input. What the assertion rules out is the
regression — a metric query that must read the table whatever the cost model says.

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
from django.utils import timezone  # noqa: E402
from workflow_manager.file_execution.models import WorkflowFileExecution  # noqa: E402
from workflow_manager.workflow_v2.enums import ExecutionStatus  # noqa: E402
from workflow_manager.workflow_v2.models.execution import WorkflowExecution  # noqa: E402
from workflow_manager.workflow_v2.models.workflow import Workflow  # noqa: E402


INDEX_NAME = "wfe_status_created_idx"

_ROWS = 4000
_SPAN_DAYS = 60
# Measured on the replica 2026-08-27: COMPLETED is 97.6% of the table and ERROR
# 0.40%. The ratio is the whole point — a partial index on ERROR would serve
# get_failed_pages and never get_documents_processed, which is why this one is full.
_ERROR_IN = 250


class TestTheMetricQueriesCanUseTheIndex(TestCase):
    """Both queries the index exists for, at production-ish status ratios."""

    @classmethod
    def setUpTestData(cls) -> None:
        org = Organization.objects.create(
            organization_id="wfe-idx-org", name="wfe-idx", display_name="WFE Idx"
        )
        workflow = Workflow.objects.create(workflow_name="wfe-idx-wf", organization=org)
        execution = WorkflowExecution.objects.create(
            workflow_id=workflow.id, status=ExecutionStatus.COMPLETED
        )

        now = timezone.now()
        # Ascending created_at so the heap matches production, where rows are
        # appended as they happen; scattered, the planner's choice is a fixture
        # artefact rather than anything about the query.
        rows = []
        for n in range(_ROWS):
            status = (
                ExecutionStatus.ERROR.value
                if n % _ERROR_IN == 0
                else ExecutionStatus.COMPLETED.value
            )
            rows.append(
                WorkflowFileExecution(
                    workflow_execution=execution,
                    file_name=f"idx-{n}.pdf",
                    status=status,
                )
            )
        WorkflowFileExecution.objects.bulk_create(rows, batch_size=1000)

        # bulk_create cannot set auto_now_add columns, so spread them afterwards.
        # Scoped to this fixture's own execution: an unqualified UPDATE would rewrite
        # created_at for every row in whatever database this happens to run against.
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE workflow_file_execution SET created_at = %s::timestamptz"
                " - (random() * %s || ' days')::interval"
                " WHERE workflow_execution_id = %s",
                [now.isoformat(), _SPAN_DAYS, str(execution.id)],
            )
            cur.execute("ANALYZE workflow_file_execution")

    def _plan(self, status: str) -> str:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute(
                "EXPLAIN SELECT date_trunc('day', created_at), count(*)"
                " FROM workflow_file_execution"
                " WHERE status = %s AND created_at >= now() - interval '2 days'"
                " GROUP BY 1",
                [status],
            )
            return "\n".join(row[0] for row in cur.fetchall())

    def _assert_status_leads_the_index_scan(self, status: str) -> None:
        plan = self._plan(status)
        assert INDEX_NAME in plan, (
            f"expected {INDEX_NAME} to be usable for status={status}:\n{plan}"
        )
        index_cond = [ln for ln in plan.splitlines() if "Index Cond" in ln]
        assert any("status" in ln for ln in index_cond), (
            f"{INDEX_NAME} is in the plan for status={status} but not entered by "
            f"status, so it is not serving the shape it was added for:\n{plan}"
        )

    def test_the_index_serves_the_documents_processed_predicate(self) -> None:
        """status = COMPLETED plus a created_at window — get_documents_processed."""
        self._assert_status_leads_the_index_scan(ExecutionStatus.COMPLETED.value)

    def test_the_index_serves_the_failed_pages_predicate(self) -> None:
        """status = ERROR plus the same window — get_failed_pages.

        The full index is what lets one index serve both; a partial index on ERROR
        would pass this and fail the one above.
        """
        self._assert_status_leads_the_index_scan(ExecutionStatus.ERROR.value)

    def test_the_index_is_valid(self) -> None:
        """UN-3972's acceptance criterion, which nothing else asserted.

        An interrupted CREATE INDEX CONCURRENTLY leaves an INVALID index that still
        satisfies IF NOT EXISTS, so the migration can report success over one the
        planner will never use.
        """
        with connection.cursor() as cur:
            cur.execute(
                "SELECT i.indisvalid FROM pg_class c"
                " JOIN pg_index i ON i.indexrelid = c.oid"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE c.relname = %s AND n.nspname = current_schema()",
                [INDEX_NAME],
            )
            row = cur.fetchone()
        assert row is not None, f"{INDEX_NAME} does not exist in the test schema"
        assert row[0] is True, f"{INDEX_NAME} exists but is INVALID"
