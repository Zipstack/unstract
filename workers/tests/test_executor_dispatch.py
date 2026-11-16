"""Tests for the file_processing → executor boundary: payload/queue routing
through the PG executor dispatcher, and an inventory canary for raw send_task calls.
"""

from __future__ import annotations

import ast
from typing import Any

import pytest
from queue_backend import FairnessKey
from queue_backend.fairness import WorkloadType
from unstract.sdk1.execution.context import ExecutionContext, Operation
from unstract.workflow_execution.executor_rpc import PgExecutionDispatcher

from .canary_helpers import iter_production_trees
from .executor_dispatch_fakes import FakeExecutorTransport, callback_signature

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


class TestPgDispatchCarriesOrgInPayload:
    """Org routing rides the enqueue payload, and ``headers=`` is rejected.

    This replaces the old ``ExecutionDispatcher`` header-forwarding suite. That
    contract is deliberately gone, not merely relocated: the PG dispatch methods
    take **no** ``headers`` argument and carry org/routing in the payload instead
    (``transport.enqueue(..., org_id=...)``). Locking the absence matters —
    three call sites kept passing ``headers=`` after the routing dispatcher was
    removed in UN-4046 and every extraction raised ``TypeError`` until they were
    found. A test that only checked the happy path would not have caught it.
    """

    def _dispatcher(self) -> tuple[PgExecutionDispatcher, FakeExecutorTransport]:
        transport = FakeExecutorTransport(result={"success": True, "data": {}})
        return PgExecutionDispatcher(transport), transport

    @pytest.mark.parametrize(
        "method", ["dispatch", "dispatch_async", "dispatch_with_callback"]
    )
    def test_org_id_travels_in_the_payload(self, method):
        d, transport = self._dispatcher()
        getattr(d, method)(_make_context(organization_id="org-1"))
        assert transport.only_call["org_id"] == "org-1"

    @pytest.mark.parametrize(
        "method", ["dispatch", "dispatch_async", "dispatch_with_callback"]
    )
    def test_no_headers_kwarg_accepted(self, method):
        """Passing ``headers=`` must fail loudly, not be silently absorbed."""
        d, _ = self._dispatcher()
        with pytest.raises(TypeError):
            getattr(d, method)(_make_context(), headers={"x-fairness-key": {}})

    @pytest.mark.parametrize(
        "method", ["dispatch", "dispatch_async", "dispatch_with_callback"]
    )
    def test_queue_derives_from_executor_name(self, method):
        d, transport = self._dispatcher()
        getattr(d, method)(_make_context(executor_name="table"))
        assert transport.queue == "celery_executor_table"

    def test_dispatch_with_callback_carries_continuations_and_task_id(self):
        """Callbacks ride the payload as continuations, not Celery link kwargs.

        The signatures are built with a real name/queue and no positional args
        because ``signature_to_continuation`` rejects all three otherwise — PG
        self-chaining routes by the row's queue and supports kwargs-only
        callbacks. A bare ``MagicMock`` passes none of those checks, so shaping
        them here is what makes the assertion meaningful.
        """
        d, transport = self._dispatcher()
        on_success = callback_signature("cb.success", queue="celery_callback")
        on_error = callback_signature("cb.error", queue="celery_callback")
        handle = d.dispatch_with_callback(
            _make_context(),
            on_success=on_success,
            on_error=on_error,
            task_id="t-1",
        )
        call = transport.only_call
        assert call["task_id"] == "t-1"
        assert handle.id == "t-1"
        assert call["on_success"]["task_name"] == "cb.success"
        assert call["on_error"]["task_name"] == "cb.error"
        assert "link" not in call and "link_error" not in call


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
    ``PgExecutionDispatcher``. Raw **string-literal**
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
            "outside ``PgExecutionDispatcher``. Use "
            "``get_executor_dispatcher().dispatch(...)`` instead so queue routing "
            "and the reply-key contract stay consistent — and because a raw "
            "send_task publishes to a broker nothing drains. (Detection "
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
