"""Tests for the file_processing → executor boundary: header forwarding
through ExecutionDispatcher and inventory canary for raw send_task calls.
"""

from __future__ import annotations

import ast
from typing import Any
from unittest.mock import MagicMock

import pytest
from celery import Celery

from queue_backend import FairnessKey
from queue_backend.fairness import FAIRNESS_HEADER_NAME, WorkloadType
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher

from .canary_helpers import iter_production_trees


def _make_context(**overrides: Any) -> ExecutionContext:
    defaults: dict[str, Any] = {
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
    return ExecutionContext(**defaults)


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
        headers = {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "workload_type": WorkloadType.NON_API.value,
            }
        }
        d.dispatch(_make_context(), timeout=1, headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    def test_dispatch_omits_headers_when_none(self):
        # Caller passes no headers ⇒ ``headers`` kwarg not forwarded
        # to send_task (preserves the call shape Celery's link /
        # link_error handling expects).
        d, app = self._patched_app()
        d.dispatch(_make_context(), timeout=1)
        assert "headers" not in app.send_task.call_args.kwargs

    def test_dispatch_async_forwards_headers(self):
        d, app = self._patched_app()
        headers = {
            FAIRNESS_HEADER_NAME: {
                "org_id": None,
                "workload_type": WorkloadType.API.value,
            }
        }
        d.dispatch_async(_make_context(), headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    def test_dispatch_async_omits_headers_when_none(self):
        d, app = self._patched_app()
        d.dispatch_async(_make_context())
        assert "headers" not in app.send_task.call_args.kwargs

    def test_dispatch_with_callback_forwards_headers(self):
        d, app = self._patched_app()
        headers = {
            FAIRNESS_HEADER_NAME: {
                "org_id": "o",
                "workload_type": WorkloadType.NON_API.value,
            }
        }
        d.dispatch_with_callback(_make_context(), headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    def test_dispatch_with_callback_omits_headers_when_none(self):
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

    def test_fairness_header_shape_orgless(self):
        # org_id=None must serialise to JSON null, not get dropped or
        # coerced — downstream consumers rely on the field's presence.
        fairness = FairnessKey(org_id=None, workload_type=WorkloadType.API)
        assert fairness.as_header() == {
            "x-fairness-key": {
                "org_id": None,
                "workload_type": "api",
                "pipeline_priority": 5,
            }
        }


class TestExecuteExtractionDispatchInventory:
    """Canary: ``execute_extraction`` must only be dispatched via
    ``ExecutionDispatcher``. Raw **string-literal**
    ``*.send_task("execute_extraction", ...)`` elsewhere is forbidden.

    Known blind spots (deliberate — widening adds AST resolution cost
    for low real-world risk on a 1-line dispatcher seam):
    * constant references (``T = "execute_extraction"; send_task(T, ...)``)
    * f-strings
    * ``apply_async`` calls
    These are documented in the assertion message so future authors
    don't trust the canary absolutely.
    """

    def test_no_raw_execute_extraction_dispatch_outside_dispatcher(self):
        offenders = [
            f"{rel}:{lineno}"
            for rel, tree in iter_production_trees()
            for lineno in _raw_execute_extraction_calls(tree)
        ]
        assert offenders == [], (
            "Production code calls ``*.send_task(\"execute_extraction\", ...)`` "
            "outside ``ExecutionDispatcher``. Use "
            "``ExecutionDispatcher.dispatch(...)`` instead so fairness "
            "headers and queue routing stay consistent. (Detection "
            "covers string-literal task names only; constant references, "
            "f-strings, and apply_async are blind spots.) Found:\n  "
            + "\n  ".join(offenders)
        )


def _raw_execute_extraction_calls(tree: ast.AST) -> list[int]:
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "send_task"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value == "execute_extraction":
            hits.append(node.lineno)
    return hits


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
