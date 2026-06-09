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

    def _make_app(self) -> MagicMock:
        app = MagicMock(name="celery_app")
        app.signature.return_value = MagicMock(name="callback_signature")
        return app

    def test_empty_header_returns_none_and_skips_chord(self):
        """Zero-batch contract preserved: barrier returns None,
        ``chord(...)`` is never called.

        Parent callers (``general/tasks.py``, ``api-deployment/tasks.py``)
        rely on this signal to handle pipeline status updates directly.
        """
        barrier = CeleryChordBarrier()
        app = self._make_app()

        with patch("queue_backend.barrier.chord") as mock_chord:
            result = barrier.enqueue(
                [],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1", "pipeline_id": "pipe-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        assert result is None
        mock_chord.assert_not_called()

    def test_non_empty_header_invokes_chord_header_then_body(self):
        """The original ``chord(header)(body)`` two-step call must
        be preserved exactly — a refactor that flattens or reorders
        these calls would change Celery's chord semantics."""
        barrier = CeleryChordBarrier()
        app = self._make_app()
        header = [MagicMock(name="h1"), MagicMock(name="h2")]

        with patch("queue_backend.barrier.chord") as mock_chord:
            chord_obj = MagicMock(name="chord_object")
            mock_chord.return_value = chord_obj

            barrier.enqueue(
                header,
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        # Step 1: chord(header)
        mock_chord.assert_called_once_with(header)
        # Step 2: chord_obj(callback_signature) — applies the chord
        chord_obj.assert_called_once_with(app.signature.return_value)

    def test_callback_signature_args_match_pre_uplift_contract(self):
        """``app.signature(task_name, kwargs=..., queue=...)`` is
        called with exactly the args the pre-Barrier helper used."""
        barrier = CeleryChordBarrier()
        app = self._make_app()
        callback_kwargs = {
            "execution_id": "exec-42",
            "pipeline_id": "pipe-7",
            "organization_id": "org-x",
        }

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.return_value = MagicMock()
            barrier.enqueue(
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

    def test_returns_chord_result_object(self):
        """The barrier handle is whatever ``chord(header)(body)``
        returns — Celery's ``AsyncResult`` in production. Callers
        log ``.id`` for chord-id tracing."""
        barrier = CeleryChordBarrier()
        app = self._make_app()

        with patch("queue_backend.barrier.chord") as mock_chord:
            chord_obj = MagicMock()
            chord_result = MagicMock(name="chord_result")
            chord_obj.return_value = chord_result
            mock_chord.return_value = chord_obj

            result = barrier.enqueue(
                [MagicMock()],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        assert result is chord_result

    def test_chord_failure_is_re_raised_after_logging(self):
        """If ``chord(...)`` raises (broker outage, serialisation
        error, etc.), the barrier logs and re-raises — never swallows.

        Without this, callers would treat broker failures as silent
        zero-task chords and skip pipeline status updates entirely.
        """
        barrier = CeleryChordBarrier()
        app = self._make_app()

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.side_effect = RuntimeError("broker exploded")

            with pytest.raises(RuntimeError, match="broker exploded"):
                barrier.enqueue(
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

    def _make_app(self) -> MagicMock:
        app = MagicMock(name="celery_app")
        app.signature.return_value = MagicMock(name="callback_signature")
        return app

    def test_fairness_header_stamped_on_callback_signature(self):
        barrier = CeleryChordBarrier()
        app = self._make_app()
        fairness = FairnessKey(
            org_id="org-1",
            workload_type=WorkloadType.API,
        )

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.return_value = MagicMock()
            barrier.enqueue(
                [MagicMock(name="h")],
                callback_task_name="process_batch_callback_api",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="api_file_processing_callback",
                app_instance=app,
                fairness=fairness,
            )

        call_args = app.signature.call_args
        headers = call_args.kwargs.get("headers")
        assert headers is not None, (
            "expected ``headers=`` kwarg on app.signature when fairness "
            "is passed"
        )
        assert headers[FAIRNESS_HEADER_NAME] == {
            "org_id": "org-1",
            "workload_type": "api",
            "pipeline_priority": 5,
        }

    def test_fairness_header_stamped_on_every_header_task(self):
        """Every batch task in the header carries the fairness header
        so PG Queue's per-task fairness scheduler can route each
        independently."""
        barrier = CeleryChordBarrier()
        app = self._make_app()
        fairness = FairnessKey(
            org_id="org-1",
            workload_type=WorkloadType.NON_API,
        )
        h1, h2, h3 = (
            MagicMock(name=f"header_task_{i}") for i in range(3)
        )

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.return_value = MagicMock()
            barrier.enqueue(
                [h1, h2, h3],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
                fairness=fairness,
            )

        expected = {
            FAIRNESS_HEADER_NAME: {
                "org_id": "org-1",
                "workload_type": "non_api",
                "pipeline_priority": 5,
            }
        }
        for task in (h1, h2, h3):
            task.set.assert_called_once_with(headers=expected)

    def test_no_fairness_no_header_added(self):
        """When ``fairness=None``, the barrier behaves byte-for-byte
        like the pre-Barrier chord call — no ``headers=`` kwarg on
        the signature, no ``.set(headers=...)`` on header tasks.

        Mixed-version rolling deploys are safe because this branch
        produces the same wire as the old direct chord call.
        """
        barrier = CeleryChordBarrier()
        app = self._make_app()
        header = [MagicMock(name="h1"), MagicMock(name="h2")]

        with patch("queue_backend.barrier.chord") as mock_chord:
            mock_chord.return_value = MagicMock()
            barrier.enqueue(
                header,
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
                app_instance=app,
            )

        # Callback signature: no headers kwarg.
        sig_call = app.signature.call_args
        assert "headers" not in sig_call.kwargs

        # Header tasks: ``.set(...)`` not called for headers stamping.
        for task in header:
            # ``set`` might be called for other reasons in production,
            # but never with ``headers=`` when fairness is None.
            for call in task.set.call_args_list:
                assert "headers" not in call.kwargs, (
                    "unexpected fairness header stamped without fairness="
                )


# --- Mixin wrapper (preserved through the Barrier uplift) ---


class TestWorkflowOrchestrationMixinCreateChord:
    """The ``WorkflowOrchestrationMixin.create_chord`` wrapper survives
    the Phase 6a uplift unchanged — it still extracts ``self.app`` and
    delegates to ``WorkflowOrchestrationUtils.create_chord_execution``
    (which now routes through ``CeleryChordBarrier``).

    Both behaviours below must be preserved by a future Phase 6b
    ``RedisDecrBarrier`` swap.
    """

    def test_create_chord_extracts_app_from_self_and_delegates(self):
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationMixin,
            WorkflowOrchestrationUtils,
        )

        task = type("FakeTask", (WorkflowOrchestrationMixin,), {})()
        task.app = MagicMock(name="celery_app")
        task.app.signature.return_value = MagicMock(name="callback_signature")

        with patch.object(
            WorkflowOrchestrationUtils, "create_chord_execution"
        ) as mock_static:
            mock_static.return_value = MagicMock(name="chord_result")
            batch = [MagicMock()]
            kwargs = {"execution_id": "exec-mixin"}
            task.create_chord(
                batch_tasks=batch,
                callback_task_name="process_batch_callback",
                callback_kwargs=kwargs,
                callback_queue="file_processing_callback",
            )

        mock_static.assert_called_once_with(
            batch,
            "process_batch_callback",
            kwargs,
            "file_processing_callback",
            task.app,
        )

    def test_create_chord_raises_when_no_app_bound(self):
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationMixin,
        )

        task = type("FakeTask", (WorkflowOrchestrationMixin,), {})()

        with pytest.raises(RuntimeError, match="Celery app instance not available"):
            task.create_chord(
                batch_tasks=[MagicMock()],
                callback_task_name="process_batch_callback",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="file_processing_callback",
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
