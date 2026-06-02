"""Tests for the file_processing -> executor boundary (PG Queue Phase 5.2)."""

from __future__ import annotations

import ast
import pathlib
from unittest.mock import MagicMock

import pytest
from celery import Celery

from queue_backend import FairnessKey
from queue_backend.fairness import FAIRNESS_HEADER_NAME, WorkloadType
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher

_WORKERS_ROOT = pathlib.Path(__file__).parent.parent
_SKIP_TOP_DIRS = frozenset(
    {"tests", "__pycache__", "htmlcov", ".venv"}
)


def _make_context(**overrides: object) -> ExecutionContext:
    defaults: dict[str, object] = {
        "executor_name": "legacy",
        "operation": Operation.EXTRACT,
        "run_id": "file-exec-1",
        "execution_source": "tool",
        "organization_id": "org-1",
        "request_id": "req-1",
        "log_events_id": "log-1",
        "execution_id": "exec-1",
        "file_execution_id": "file-exec-1",
        "executor_params": {"adapter_instance_id": "a"},
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)  # type: ignore[arg-type]


class TestExecutionDispatcherForwardsHeaders:
    """``ExecutionDispatcher`` propagates the ``headers`` kwarg to Celery."""

    def _patched_app(self) -> tuple[ExecutionDispatcher, MagicMock]:
        app = MagicMock(spec=Celery)
        async_result = MagicMock()
        async_result.id = "task-1"
        async_result.get.return_value = {"success": True, "data": {}}
        app.send_task.return_value = async_result
        return ExecutionDispatcher(celery_app=app), app

    def test_dispatch_forwards_headers(self):
        d, app = self._patched_app()
        headers = {FAIRNESS_HEADER_NAME: {"org_id": "org-1", "workload_type": "etl"}}
        d.dispatch(_make_context(), timeout=1, headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    def test_dispatch_omits_headers_when_none(self):
        d, app = self._patched_app()
        d.dispatch(_make_context(), timeout=1)
        # Matches the pre-Phase-5.2 send_task call shape exactly —
        # no ``headers`` kwarg when the caller doesn't pass one.
        assert "headers" not in app.send_task.call_args.kwargs

    def test_dispatch_async_forwards_headers(self):
        d, app = self._patched_app()
        headers = {FAIRNESS_HEADER_NAME: {"org_id": None, "workload_type": "api"}}
        d.dispatch_async(_make_context(), headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    def test_dispatch_with_callback_forwards_headers(self):
        d, app = self._patched_app()
        headers = {FAIRNESS_HEADER_NAME: {"org_id": "o", "workload_type": "etl"}}
        d.dispatch_with_callback(_make_context(), headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    def test_dispatch_with_callback_omits_headers_when_none(self):
        # When headers is None the kwarg should not be passed at all
        # (preserves the pre-change call shape for Celery's link/
        # link_error handling).
        d, app = self._patched_app()
        d.dispatch_with_callback(_make_context())
        assert "headers" not in app.send_task.call_args.kwargs


class TestFairnessKeyComposesWithHeaders:
    """The header that producers actually build round-trips correctly."""

    def test_fairness_header_shape(self):
        fairness = FairnessKey(
            org_id="org-1", workload_type=WorkloadType.NON_API, pipeline_priority=5
        )
        assert fairness.as_header() == {
            "x-fairness-key": {
                "org_id": "org-1",
                "workload_type": "non_api",
                "pipeline_priority": 5,
            }
        }


class TestExecuteExtractionDispatchInventory:
    """Canary: ``execute_extraction`` must only be dispatched via
    ``ExecutionDispatcher``. Raw ``*.send_task("execute_extraction", ...)``
    elsewhere bypasses the dispatcher's fairness-header plumbing and
    must not happen."""

    def test_no_raw_execute_extraction_dispatch_outside_dispatcher(self):
        offenders = [
            f"{rel}:{lineno}"
            for rel, tree in _iter_production_trees()
            for lineno in _raw_execute_extraction_calls(tree)
        ]
        assert offenders == [], (
            "Production code calls ``*.send_task(\"execute_extraction\", ...)`` "
            "outside ``ExecutionDispatcher``. Use ``ExecutionDispatcher.dispatch(...)`` "
            "instead so fairness headers and queue routing stay consistent. "
            "Found:\n  " + "\n  ".join(offenders)
        )


def _iter_production_trees() -> list[tuple[pathlib.Path, ast.AST]]:
    out: list[tuple[pathlib.Path, ast.AST]] = []
    for py in _WORKERS_ROOT.rglob("*.py"):
        rel = py.relative_to(_WORKERS_ROOT)
        if rel.parts and rel.parts[0] in _SKIP_TOP_DIRS:
            continue
        try:
            tree = ast.parse(py.read_text(), filename=str(py))
        except SyntaxError:
            continue
        out.append((rel, tree))
    return out


def _raw_execute_extraction_calls(tree: ast.AST) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "send_task"):
            continue
        # First positional arg must be the task name string.
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value == "execute_extraction":
            hits.append(node.lineno)
    return hits


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
