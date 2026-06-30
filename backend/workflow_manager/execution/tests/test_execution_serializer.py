"""ExecutionSerializer file-count reconciliation (UN-3657).

A terminal *failure* run (ERROR/STOPPED) must not report files as still
"in progress": the UI derives in-progress as ``total - successful - failed``,
so every non-successful file in a finished failure run has to land in
``failed`` — including files that never got a ``file_execution`` row because
orchestration aborted before creating them. COMPLETED and live
(PENDING/EXECUTING) runs must keep the exact row-count behaviour.

ORM is mocked, so no test database is required.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from workflow_manager.execution.serializer.execution import (  # noqa: E402
    ExecutionSerializer,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus  # noqa: E402


def _execution(status, total_files, *, completed=0, errored=0):
    """A WorkflowExecution stand-in whose ``file_executions`` row counts are
    fixed per status.
    """
    obj = MagicMock()
    obj.status = status
    obj.total_files = total_files

    def _filter(status=None, **_kwargs):
        result = MagicMock()
        result.count.return_value = {
            ExecutionStatus.COMPLETED.value: completed,
            ExecutionStatus.ERROR.value: errored,
        }.get(status, 0)
        return result

    obj.file_executions.filter.side_effect = _filter
    return obj


class TestFailedFileReconciliation:
    serializer = ExecutionSerializer()

    def test_error_run_with_no_rows_counts_all_as_failed(self):
        # The exec 4b180f05 case: ERROR before any file_execution row exists.
        obj = _execution(ExecutionStatus.ERROR.value, 2)
        assert self.serializer.get_successful_files(obj) == 0
        assert (
            self.serializer.get_failed_files(obj) == 2
        )  # was 0 -> phantom "2 in progress"

    def test_error_run_partial_rows_reconciles_unaccounted(self):
        # total 3: 1 completed, 1 errored row, 1 never created -> 2 failed.
        obj = _execution(ExecutionStatus.ERROR.value, 3, completed=1, errored=1)
        assert self.serializer.get_failed_files(obj) == 2

    def test_stopped_run_reconciles(self):
        # STOPPED is a failure terminal state: 3 of 5 done -> 2 failed, 0 in-progress.
        obj = _execution(ExecutionStatus.STOPPED.value, 5, completed=3)
        assert self.serializer.get_failed_files(obj) == 2

    def test_completed_run_uses_row_count_unchanged(self):
        # Success path is untouched: failed == ERROR-row count, not reconciled.
        clean = _execution(ExecutionStatus.COMPLETED.value, 2, completed=2)
        assert self.serializer.get_failed_files(clean) == 0
        partial = _execution(ExecutionStatus.COMPLETED.value, 2, completed=1, errored=1)
        assert self.serializer.get_failed_files(partial) == 1

    def test_live_run_uses_row_count_unchanged(self):
        # An in-flight run keeps real-time row counts (no reconcile), so
        # genuinely-pending files are NOT prematurely marked failed.
        obj = _execution(ExecutionStatus.EXECUTING.value, 2)
        assert self.serializer.get_failed_files(obj) == 0

    def test_successful_over_total_is_clamped_not_negative(self):
        # Defensive: a bad/stale count can't produce a negative failed count.
        obj = _execution(ExecutionStatus.ERROR.value, 1, completed=2)
        assert self.serializer.get_failed_files(obj) == 0
