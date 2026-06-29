"""Tests for ``WorkflowOrchestrationUtils.pg_failure_file_counts`` (UN-3652 / B).

The helper is the gate that keeps the PG-orchestration-failure counter
reconciliation entirely under ``pg_queue_enabled``:

- PG transport → mark the attempted files failed (``successful=0``,
  ``failed=total``) so a failed execution reads "N failed", not "N in progress".
- Every non-PG transport → ``{}`` (no change), so the Celery failure path stays
  byte-identical.
"""

from __future__ import annotations

import pytest
from shared.workflow.execution.orchestration_utils import WorkflowOrchestrationUtils

from unstract.core.data_models import WorkflowTransport

_PG = WorkflowTransport.PG_QUEUE.value
_CELERY = WorkflowTransport.CELERY.value


class TestPgFailureFileCounts:
    @pytest.mark.parametrize("total", [0, 1, 2, 50])
    def test_pg_marks_attempted_files_failed(self, total):
        # total_files is included so the backend update_status serializer accepts
        # the aggregates ("total_files is required when file aggregates are
        # provided"); successful+failed (0+total) must also be <= total.
        assert WorkflowOrchestrationUtils.pg_failure_file_counts(_PG, total) == {
            "total_files": total,
            "successful_files": 0,
            "failed_files": total,
        }

    @pytest.mark.parametrize("total", [0, 1, 2, 50])
    def test_pg_counts_satisfy_serializer_constraints(self, total):
        # Mirror internal_serializers validation: total present, and
        # successful + failed <= total.
        c = WorkflowOrchestrationUtils.pg_failure_file_counts(_PG, total)
        assert "total_files" in c
        assert c["successful_files"] + c["failed_files"] <= c["total_files"]

    def test_celery_is_noop(self):
        # The non-PG branch must contribute nothing → Celery path byte-identical.
        assert WorkflowOrchestrationUtils.pg_failure_file_counts(_CELERY, 2) == {}

    @pytest.mark.parametrize("transport", ["", "celery", "unknown", "CELERY"])
    def test_non_pg_transports_are_noop(self, transport):
        assert WorkflowOrchestrationUtils.pg_failure_file_counts(transport, 5) == {}

    def test_result_zeroes_ui_in_progress(self):
        # UI derives in-progress = total - successful - failed; the PG counts must
        # drive that to 0 for a fully-failed orchestration.
        counts = WorkflowOrchestrationUtils.pg_failure_file_counts(_PG, 3)
        in_progress = 3 - counts["successful_files"] - counts["failed_files"]
        assert in_progress == 0
