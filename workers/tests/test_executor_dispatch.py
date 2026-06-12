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
from queue_backend.fairness import WorkloadType
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.sdk1.execution.dispatcher import ExecutionDispatcher

from .canary_helpers import iter_production_trees

# Promote ``UserWarning`` from ``iter_production_trees`` (emitted on
# unparseable production files) to a test failure. Without this an
# unparseable file would be silently dropped from the audited tree
# and the canary would pass vacuously over a smaller set —
# exactly the failure mode the helper claims to prevent.
pytestmark = pytest.mark.filterwarnings("error::UserWarning")


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

    # The three dispatch entry points share the same header-forwarding
    # contract via ``_build_send_kwargs``; parametrize over them so a
    # divergence (e.g. one method dropping ``headers=``) surfaces with
    # per-method failure granularity via the parametrize IDs.
    @pytest.mark.parametrize(
        "method", ["dispatch", "dispatch_async", "dispatch_with_callback"]
    )
    def test_forwards_headers(self, method):
        # Use ``FairnessKey.as_header()`` as the fixture rather than
        # hand-built dicts so the test exercises the exact wire shape
        # real producers emit (including ``pipeline_priority``).
        headers = FairnessKey(
            org_id="org-1", workload_type=WorkloadType.NON_API
        ).as_header()
        d, app = self._patched_app()
        getattr(d, method)(_make_context(), headers=headers)
        assert app.send_task.call_args.kwargs["headers"] == headers

    @pytest.mark.parametrize(
        "method", ["dispatch", "dispatch_async", "dispatch_with_callback"]
    )
    def test_omits_headers_when_none(self, method):
        # Caller passes no headers ⇒ ``headers`` kwarg not forwarded
        # to send_task (preserves the call shape Celery's link /
        # link_error handling expects).
        d, app = self._patched_app()
        getattr(d, method)(_make_context())
        assert "headers" not in app.send_task.call_args.kwargs

    @pytest.mark.parametrize(
        "method", ["dispatch", "dispatch_async", "dispatch_with_callback"]
    )
    def test_omits_headers_when_empty_dict(self, method):
        """Empty header dicts are dropped (treated as a no-headers
        call). ``FairnessKey.as_header()`` can never legitimately
        return ``{}`` — forwarding it would document a producer-side
        build bug rather than catch it.
        """
        d, app = self._patched_app()
        getattr(d, method)(_make_context(), headers={})
        assert "headers" not in app.send_task.call_args.kwargs

    def test_dispatch_with_callback_combines_headers_and_callbacks(self):
        """All four optional kwargs (headers, on_success, on_error,
        task_id) land on the same ``send_task`` call. A merge bug in
        ``_build_send_kwargs`` would slip through the single-kwarg
        forwarding tests above.
        """
        from celery.canvas import Signature

        d, app = self._patched_app()
        headers = FairnessKey(
            org_id="org-1", workload_type=WorkloadType.NON_API
        ).as_header()
        on_success = MagicMock(spec=Signature)
        on_error = MagicMock(spec=Signature)
        d.dispatch_with_callback(
            _make_context(),
            on_success=on_success,
            on_error=on_error,
            task_id="t-1",
            headers=headers,
        )
        kwargs = app.send_task.call_args.kwargs
        assert kwargs["headers"] == headers
        assert kwargs["link"] is on_success
        assert kwargs["link_error"] is on_error
        assert kwargs["task_id"] == "t-1"


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

    def test_detector_matches_string_literal_send_task(self):
        """Positive-detection lock: feed a known-bad snippet and
        assert the detector flags it. Without this the canary above
        could silently rot (e.g. ``ast.walk`` returning nothing) and
        always report ``offenders == []`` regardless of the tree.
        """
        bad = ast.parse('app.send_task("execute_extraction", args=[])')
        assert _raw_execute_extraction_calls(bad) == [1]

    def test_detector_skips_documented_blind_spots(self):
        """Lock the deliberate blind spots in the assertion message:
        a constant reference, an f-string, and an ``apply_async`` call
        all evade the canary. Documenting them as tests means a future
        author who widens the detector intentionally has to update
        these assertions — flagging that the canary scope changed.
        """
        constant_ref = ast.parse(
            "T = 'execute_extraction'\napp.send_task(T, args=[])"
        )
        fstring = ast.parse(
            'name = "extraction"\napp.send_task(f"execute_{name}", args=[])'
        )
        apply_async = ast.parse(
            'app.apply_async("execute_extraction", args=[])'
        )
        assert _raw_execute_extraction_calls(constant_ref) == []
        assert _raw_execute_extraction_calls(fstring) == []
        assert _raw_execute_extraction_calls(apply_async) == []


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
