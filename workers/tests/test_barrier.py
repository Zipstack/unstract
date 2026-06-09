"""Characterisation tests for the ``Barrier`` abstraction (PG Queue Phase 6a).

The two production chord call sites
(``WorkflowOrchestrationUtils.create_chord_execution`` and
``api-deployment/tasks.py``'s inline chord) were lifted behind
``CeleryChordBarrier`` so a future Phase 6b can swap in
``RedisDecrBarrier`` (or PG-based) implementations without touching
call sites.

Three layers of coverage:

1. **Barrier protocol shape** — ``CeleryChordBarrier`` satisfies the
   ``Barrier`` Protocol and ``AsyncResult`` satisfies ``BarrierHandle``.
2. **Wire equivalence with the pre-Barrier chord call** — given the
   same args, ``CeleryChordBarrier.enqueue(...)`` produces the same
   ``chord(header)(body)`` invocation, the same ``app.signature(...)``
   args, and the same return value. A regression that bypasses the
   abstraction or alters the wire surface fails one of these tests.
3. **Fairness plumbing** — when ``fairness=`` is passed, the fairness
   header is attached to every enqueued task and to the callback
   (closes Phase 5.1's chord-fairness gap that was deliberately
   scoped out).

The single ``chord(...)`` call still lives in
``queue_backend/barrier.py`` (asserted by the inventory test in
``test_chord_sites_characterisation.py``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from queue_backend import (
    Barrier,
    BarrierHandle,
    CeleryChordBarrier,
    FairnessKey,
)
from queue_backend.fairness import FAIRNESS_HEADER_NAME, WorkloadType


@pytest.fixture
def app() -> MagicMock:
    """Celery-app-shaped mock with a working ``.signature(...)``.

    Used by every test that drives ``CeleryChordBarrier.enqueue(...)``.
    Shared via fixture rather than a per-class ``_make_app`` helper to
    keep test classes free of boilerplate (SonarCloud S4144
    duplication).
    """
    mock = MagicMock(name="celery_app")
    mock.signature.return_value = MagicMock(name="callback_signature")
    return mock


@pytest.fixture
def mock_chord():
    """Patch ``queue_backend.barrier.chord`` and yield the mock.

    Every wire-equivalence / fairness test patches the same import
    target — extracting to a fixture removes ~8 identical
    ``with patch(...) as mock_chord:`` lines (SonarCloud S4144
    duplication).
    """
    with patch("queue_backend.barrier.chord") as m:
        m.return_value = MagicMock(name="chord_object")
        yield m


# --- Protocol shape ---


class TestBarrierProtocolShape:
    def test_celery_chord_barrier_satisfies_protocol(self):
        """``CeleryChordBarrier`` is structurally a ``Barrier``.

        Pinned so Phase 6b's ``RedisDecrBarrier`` can be substituted at
        any call site without runtime ``AttributeError``.
        """
        barrier: Barrier = CeleryChordBarrier()
        assert callable(getattr(barrier, "enqueue", None))

    def test_barrier_handle_protocol_is_minimal(self):
        """``BarrierHandle`` only requires ``id: str`` — celery's
        ``AsyncResult`` satisfies this. Future substrate handles must
        too so existing chord-id logging keeps working."""
        # MagicMock with .id attribute is structurally a BarrierHandle.
        handle = MagicMock()
        handle.id = "task-1"
        # Treating it as a BarrierHandle at runtime works (Python's
        # Protocols are duck-typed; this test pins the contract).
        h: BarrierHandle = handle
        assert h.id == "task-1"


# --- Wire equivalence with the pre-Barrier chord call ---


class TestCeleryChordBarrierWireEquivalence:
    """``CeleryChordBarrier.enqueue(...)`` must produce the same
    ``chord(batch_tasks)(callback_signature)`` invocation that the
    original inline ``chord(...)`` calls produced — modulo the
    additive ``x-fairness-key`` header that the barrier optionally
    stamps onto signatures.
    """

    def test_empty_header_returns_none_and_skips_chord(self, app, mock_chord):
        """Zero-batch contract preserved: barrier returns None,
        ``chord(...)`` is never called.

        Parent callers (``general/tasks.py``, ``api-deployment/tasks.py``)
        rely on this signal to handle pipeline status updates directly.
        """
        result = CeleryChordBarrier().enqueue(
            [],
            callback_task_name="process_batch_callback",
            callback_kwargs={"execution_id": "exec-1", "pipeline_id": "pipe-1"},
            callback_queue="file_processing_callback",
            app_instance=app,
        )

        assert result is None
        mock_chord.assert_not_called()

    def test_non_empty_header_invokes_chord_header_then_body(self, app, mock_chord):
        """The original ``chord(header)(body)`` two-step call must
        be preserved exactly — a refactor that flattens or reorders
        these calls would change Celery's chord semantics."""
        header = [MagicMock(name="h1"), MagicMock(name="h2")]

        CeleryChordBarrier().enqueue(
            header,
            callback_task_name="process_batch_callback",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="file_processing_callback",
            app_instance=app,
        )

        # Step 1: chord(header)
        mock_chord.assert_called_once_with(header)
        # Step 2: chord_obj(callback_signature) — applies the chord
        mock_chord.return_value.assert_called_once_with(app.signature.return_value)

    def test_callback_signature_args_match_pre_uplift_contract(self, app, mock_chord):
        """``app.signature(task_name, kwargs=..., queue=...)`` is
        called with exactly the args the pre-Barrier helper used."""
        callback_kwargs = {
            "execution_id": "exec-42",
            "pipeline_id": "pipe-7",
            "organization_id": "org-x",
        }

        CeleryChordBarrier().enqueue(
            [MagicMock(name="h")],
            callback_task_name="process_batch_callback_api",
            callback_kwargs=callback_kwargs,
            callback_queue="api_file_processing_callback",
            app_instance=app,
        )

        # Without ``fairness=``, no ``headers=`` kwarg on the signature
        # call — matches the pre-Barrier wire byte-for-byte.
        app.signature.assert_called_once_with(
            "process_batch_callback_api",
            kwargs=callback_kwargs,
            queue="api_file_processing_callback",
        )

    def test_returns_chord_result_object(self, app, mock_chord):
        """The barrier handle is whatever ``chord(header)(body)``
        returns — Celery's ``AsyncResult`` in production. Callers
        log ``.id`` for chord-id tracing."""
        chord_result = MagicMock(name="chord_result")
        mock_chord.return_value.return_value = chord_result

        result = CeleryChordBarrier().enqueue(
            [MagicMock()],
            callback_task_name="process_batch_callback",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="file_processing_callback",
            app_instance=app,
        )

        assert result is chord_result

    def test_chord_failure_is_re_raised_after_logging(self, app, mock_chord):
        """If ``chord(...)`` raises (broker outage, serialisation
        error, etc.), the barrier logs and re-raises — never swallows.

        Without this, callers would treat broker failures as silent
        zero-task chords and skip pipeline status updates entirely.
        """
        mock_chord.side_effect = RuntimeError("broker exploded")

        with pytest.raises(RuntimeError, match="broker exploded"):
            CeleryChordBarrier().enqueue(
                [MagicMock()],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )


# --- Fairness plumbing ---


class TestCeleryChordBarrierFairnessHeader:
    """When ``fairness=FairnessKey(...)`` is passed, the barrier
    stamps ``x-fairness-key`` on every header task and the callback.

    Closes the chord-fairness gap from Phase 5.1: bare ``dispatch()``
    calls carried fairness; the two chord call sites didn't (they
    bypassed ``dispatch()`` entirely). After this Phase 6a uplift,
    every queue-crossing payload on the workflow-execution path now
    carries the fairness slot.
    """

    def test_fairness_header_stamped_on_callback_signature(self, app, mock_chord):
        CeleryChordBarrier().enqueue(
            [MagicMock(name="h")],
            callback_task_name="process_batch_callback_api",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="api_file_processing_callback",
            app_instance=app,
            fairness=FairnessKey(org_id="org-1", workload_type=WorkloadType.API),
        )

        headers = app.signature.call_args.kwargs.get("headers")
        assert headers is not None, (
            "expected ``headers=`` kwarg on app.signature when fairness "
            "is passed"
        )
        assert headers[FAIRNESS_HEADER_NAME] == {
            "org_id": "org-1",
            "workload_type": "api",
            "pipeline_priority": 5,
        }

    def test_fairness_header_stamped_on_every_header_task(self, app, mock_chord):
        """Every batch task in the header carries the fairness header
        so PG Queue's per-task fairness scheduler can route each
        independently.

        Header signatures are stamped via ``Signature.clone().set(...)``
        (not in-place ``.set(...)``) — clone avoids cross-tenant
        header leakage if a future retry path or signature cache ever
        re-uses the original ``header_tasks`` list with a different
        ``FairnessKey``. The test asserts ``.clone().set(headers=...)``
        is called on each original task.
        """
        h1, h2, h3 = (MagicMock(name=f"header_task_{i}") for i in range(3))

        CeleryChordBarrier().enqueue(
            [h1, h2, h3],
            callback_task_name="process_batch_callback",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="file_processing_callback",
            app_instance=app,
            fairness=FairnessKey(org_id="org-1", workload_type=WorkloadType.NON_API),
        )

        expected = {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "workload_type": "non_api",
                "pipeline_priority": 5,
            }
        }
        for task in (h1, h2, h3):
            # ``.clone()`` produces a fresh signature; the ``.set(...)``
            # then attaches the fairness header to the clone, leaving
            # the original ``task`` unchanged.
            task.clone.assert_called_once_with()
            task.clone.return_value.set.assert_called_once_with(headers=expected)
            # Direct ``.set(...)`` on the original is NEVER called —
            # the whole point of the clone-and-set pattern.
            task.set.assert_not_called()

    def test_no_fairness_no_header_added(self, app, mock_chord):
        """When ``fairness=None``, the barrier behaves byte-for-byte
        like the pre-Barrier chord call — no ``headers=`` kwarg on
        the signature, no ``.set(headers=...)`` on header tasks.

        Mixed-version rolling deploys are safe because this branch
        produces the same wire as the old direct chord call.
        """
        header = [MagicMock(name="h1"), MagicMock(name="h2")]

        CeleryChordBarrier().enqueue(
            header,
            callback_task_name="process_batch_callback",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="file_processing_callback",
            app_instance=app,
        )

        # Callback signature: no headers kwarg.
        assert "headers" not in app.signature.call_args.kwargs

        # Header tasks: ``.set(...)`` not called for headers stamping.
        for task in header:
            # ``set`` might be called for other reasons in production,
            # but never with ``headers=`` when fairness is None.
            for call in task.set.call_args_list:
                assert "headers" not in call.kwargs, (
                    "unexpected fairness header stamped without fairness="
                )


# --- Singleton routing (pins the _BARRIER dispatch point) ---


class TestOrchestrationUtilsRoutesThroughSingleton:
    """Pin the ``WorkflowOrchestrationUtils.create_chord_execution``
    routing to the module-level ``_BARRIER`` singleton.

    A refactor that bypasses the singleton (e.g. inlining
    ``CeleryChordBarrier().enqueue(...)`` inside the static method,
    or going back to a direct ``chord(...)`` call) would still pass
    the inventory canary in ``test_chord_sites_characterisation.py``
    as long as ``chord(...)`` lives somewhere inside ``barrier.py``.
    This test closes that gap so the singleton is the unambiguous
    single dispatch point — ready for Phase 6b's factory swap.
    """

    def test_create_chord_execution_delegates_to_module_barrier(self):
        from shared.workflow.execution import orchestration_utils
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app_mock = MagicMock(name="celery_app")
        app_mock.signature.return_value = MagicMock(name="callback_signature")
        batch = [MagicMock(name="h1")]
        fairness = FairnessKey(org_id="org-1", workload_type=WorkloadType.API)

        with patch.object(orchestration_utils, "_BARRIER") as mock_barrier:
            mock_barrier.enqueue.return_value = MagicMock(name="result")
            WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=batch,
                callback_task_name="process_batch_callback_api",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="api_file_processing_callback",
                app_instance=app_mock,
                fairness=fairness,
            )

        mock_barrier.enqueue.assert_called_once_with(
            batch,
            callback_task_name="process_batch_callback_api",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="api_file_processing_callback",
            app_instance=app_mock,
            fairness=fairness,
        )


# --- Call-site fairness contracts ---


class TestCallSiteFairnessContracts:
    """Pin the ``FairnessKey`` shape each production call site declares.

    A refactor that swaps the workload types, drops the ``fairness=``
    kwarg, or transposes the org-id source goes undetected by the
    isolated barrier tests above. These tests assert the contract at
    the call site boundary.
    """

    def test_api_deployment_declares_api_workload_with_schema_name(self):
        """``api-deployment/tasks.py`` must pass ``WorkloadType.API``
        and ``org_id=str(schema_name)``."""
        import importlib
        import inspect

        api_tasks = importlib.import_module("api-deployment.tasks") if False else None
        # ``api-deployment`` is not a valid Python identifier — import by path.
        import importlib.util

        src = (
            inspect.getfile(__import__("queue_backend.barrier", fromlist=["a"]))
        )
        # Re-derive workers root.
        import pathlib

        api_tasks_path = (
            pathlib.Path(src).parent.parent / "api-deployment" / "tasks.py"
        )
        text = api_tasks_path.read_text()

        # Assert the FairnessKey block at the chord call site declares
        # the contract this PR's commit message claims it does.
        assert "fairness=FairnessKey(" in text
        assert "workload_type=WorkloadType.API" in text
        assert "org_id=str(schema_name)" in text

    def test_general_declares_non_api_workload_with_organization_id(self):
        """``general/tasks.py`` must pass ``WorkloadType.NON_API`` and
        ``org_id=organization_id``."""
        import inspect
        import pathlib

        src = inspect.getfile(__import__("queue_backend.barrier", fromlist=["a"]))
        general_tasks_path = (
            pathlib.Path(src).parent.parent / "general" / "tasks.py"
        )
        text = general_tasks_path.read_text()

        assert "fairness=FairnessKey(" in text
        assert "workload_type=WorkloadType.NON_API" in text
        assert "org_id=organization_id" in text


# --- Zero-files contract (regression pin for T1) ---


class TestApiDeploymentZeroFilesContract:
    """Pin the api-deployment zero-files handler.

    Before the Barrier uplift, ``chord(empty)(callback)`` returned a
    truthy ``AsyncResult`` (Celery fires the body immediately with
    ``[]``). The Barrier returns ``None`` for empty headers, so the
    caller now has to handle the ``None`` case explicitly — otherwise
    the existing ``if not result: raise`` would map zero-files runs
    to ``ExecutionStatus.ERROR``.

    The post-Barrier handler explicitly dispatches the callback with
    an empty result list to preserve pre-Barrier behaviour
    byte-for-byte: ``workflow_execution_status`` updates, API result
    caching, and pipeline notifications all run exactly as they would
    have pre-Barrier. Unreachable in practice (upstream guarantees
    non-empty ``created_files``) but this test pins the defensive
    contract so a future refactor doesn't silently regress.
    """

    def test_api_deployment_zero_files_dispatches_callback_with_empty_list(self):
        import inspect
        import pathlib

        src = inspect.getfile(__import__("queue_backend.barrier", fromlist=["a"]))
        api_tasks_path = (
            pathlib.Path(src).parent.parent / "api-deployment" / "tasks.py"
        )
        text = api_tasks_path.read_text()

        # Defensive branch present and dispatches the callback via
        # the seam (queue_backend.dispatch), not raw send_task — the
        # dispatch-sites canary in test_dispatch_sites_characterisation.py
        # enforces that. The literal strings are part of the
        # externally-observable response + behaviour contract.
        assert "if not batch_tasks:" in text
        assert "dispatch(" in text  # routed through queue_backend seam
        assert '"process_batch_callback_api"' in text  # callback fired
        assert "args=[[]]" in text  # body=[] matches chord-empty semantic
        assert '"batches_created": 0' in text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
