"""ExecutionSerializer file-count reconciliation (UN-3657).

A terminal *failure* run (ERROR/STOPPED) must not report files as still "in
progress": the UI derives in-progress as ``total - successful - failed``, so
every non-successful file in a finished failure run has to land in ``failed`` —
including files that never got a ``file_execution`` row. COMPLETED and live
(PENDING/EXECUTING) runs keep the exact row-count behaviour.

DB-free and app-registry-free: the heavy ``WorkflowExecution`` model is stubbed
in ``sys.modules`` before importing the serializer (mirrors
``usage_v2/tests/test_helper.py`` / ``pg_queue/tests/test_producer.py``), so no
``django.setup()`` / live DB is needed — the methods under test are pure. The
real ``ExecutionStatus`` enum (no Django) is kept for its ``is_failure`` logic.
"""

from __future__ import annotations

import logging
import os
import sys
import types
from unittest.mock import MagicMock

# Force (not setdefault): a dev shell that already exports DJANGO_SETTINGS_MODULE
# (backend.settings.dev / .cloud) would otherwise redirect collection to a module
# that may not exist here. DRF reads settings lazily; no django.setup() is run.
os.environ["DJANGO_SETTINGS_MODULE"] = "backend.settings.test"

# Stub the model module so importing the serializer needs no app registry / DB.
_models_stub = types.ModuleType("workflow_manager.workflow_v2.models")
_models_stub.WorkflowExecution = type("WorkflowExecution", (), {})
sys.modules["workflow_manager.workflow_v2.models"] = _models_stub

from workflow_manager.execution.serializer.execution import (  # noqa: E402
    ExecutionSerializer,
)
from workflow_manager.workflow_v2.enums import ExecutionStatus  # noqa: E402

_LOGGER = "workflow_manager.execution.serializer.execution"
_ids = iter(range(1, 100_000))


def _execution(status, total_files, *, completed=0, errored=0):
    """A WorkflowExecution stand-in with fixed per-status row counts and a unique
    id (so the serializer's per-(id, status) count memo never collides across
    cases).
    """
    obj = MagicMock()
    obj.id = f"exec-{next(_ids)}"
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


def _assert_no_phantom_in_progress(serializer, obj):
    """The real contract: a finished run leaves zero files "in progress"."""
    in_progress = (
        obj.total_files
        - serializer.get_successful_files(obj)
        - serializer.get_failed_files(obj)
    )
    assert in_progress == 0


class TestFailedFileReconciliation:
    def test_error_run_with_no_rows_counts_all_as_failed(self):
        # ERROR before any file_execution row exists (the observed case).
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.ERROR.value, 2)
        assert s.get_successful_files(obj) == 0
        assert s.get_failed_files(obj) == 2  # was 0 -> phantom "2 in progress"
        _assert_no_phantom_in_progress(s, obj)

    def test_error_run_partial_rows_reconciles_unaccounted(self):
        # total 3: 1 completed, 1 errored row, 1 never created -> 2 failed.
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.ERROR.value, 3, completed=1, errored=1)
        assert s.get_failed_files(obj) == 2
        _assert_no_phantom_in_progress(s, obj)

    def test_stopped_run_reconciles(self):
        # STOPPED is a failure terminal state: 3 of 5 done -> 2 failed.
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.STOPPED.value, 5, completed=3)
        assert s.get_failed_files(obj) == 2
        _assert_no_phantom_in_progress(s, obj)

    def test_completed_run_uses_row_count_unchanged(self):
        s = ExecutionSerializer()
        clean = _execution(ExecutionStatus.COMPLETED.value, 2, completed=2)
        assert s.get_failed_files(clean) == 0
        partial = _execution(ExecutionStatus.COMPLETED.value, 2, completed=1, errored=1)
        assert s.get_failed_files(partial) == 1

    def test_completed_run_not_reconciled_even_with_unaccounted(self):
        # Deliberate asymmetry: a COMPLETED run is NOT reconciled — failed stays
        # the ERROR-row count, not total - completed. Pins the decision so a
        # future "reconcile everything" change fails here.
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.COMPLETED.value, 3, completed=1, errored=1)
        assert s.get_failed_files(obj) == 1  # ERROR rows, NOT total-completed (=2)

    def test_live_run_uses_row_count_unchanged(self):
        # In-flight run keeps real-time row counts — genuinely-pending files are
        # NOT prematurely marked failed.
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.EXECUTING.value, 2)
        assert s.get_failed_files(obj) == 0

    def test_drift_does_not_under_report_below_error_rows(self, caplog):
        # total_files stale/low vs real rows: 3 completed + 2 error, total=2.
        # Must NOT report 0 (the naive total-successful); keep the 2 real ERROR
        # rows and warn — the inverse of the phantom bug.
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.ERROR.value, 2, completed=3, errored=2)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert s.get_failed_files(obj) == 2
        assert any("exceed total_files" in r.message for r in caplog.records)

    def test_successful_over_total_clamps_with_warning(self, caplog):
        # Impossible count (more completed than total) — clamp to the safe value
        # but log the anomaly rather than erasing it silently.
        s = ExecutionSerializer()
        obj = _execution(ExecutionStatus.ERROR.value, 1, completed=2)
        with caplog.at_level(logging.WARNING, logger=_LOGGER):
            assert s.get_failed_files(obj) == 0
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_unknown_status_returns_error_rows_and_never_raises(self):
        # is_failure swallows ValueError -> else (row-count) path. A malformed
        # status must never raise (a raise would 500 the executions list).
        s = ExecutionSerializer()
        obj = _execution("GARBAGE", 5, completed=1, errored=1)
        assert s.get_failed_files(obj) == 1  # ERROR-row count, no reconcile, no raise
