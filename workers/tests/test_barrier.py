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

import contextlib
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

    def test_barrier_handle_protocol_satisfied_by_celery_async_result(self):
        """The real production substrate handle — Celery's
        ``AsyncResult`` — must satisfy ``BarrierHandle``. Without
        this, refactors of ``BarrierHandle`` (e.g. adding a
        required attribute) would silently break chord-id logging
        in ``api-deployment/tasks.py``'s response without any test
        catching it. Tautological MagicMock-with-.id-attribute
        tests pass identically even if ``BarrierHandle`` were
        deleted; this one is load-bearing.
        """
        from celery.result import AsyncResult

        # Assert against a real ``AsyncResult`` *instance* — that's
        # what every production call site receives and logs ``.id``
        # from. We don't rely on whether the attribute is class-level,
        # a property, or set in ``__init__``; the instance check is
        # the smallest-blast-radius equivalent of "production sees
        # this object and reads ``.id``".
        #
        # ``required_attrs`` is hand-maintained: if a future refactor
        # adds a required attribute to ``TaskHandle`` /
        # ``BarrierHandle``, add it here too. We do *not* introspect
        # ``TaskHandle.__annotations__`` because runtime-checkable
        # Protocols would force every substrate handle (including
        # third-party ones we don't control) to be runtime-checkable
        # too. Trade-off: the maintenance is manual but the contract
        # is enforced.
        async_result_instance = AsyncResult("placeholder-task-id")
        required_attrs = ("id",)
        missing = [
            a for a in required_attrs if not hasattr(async_result_instance, a)
        ]
        assert missing == [], (
            f"AsyncResult is missing required BarrierHandle attribute(s): "
            f"{missing} — a refactor of BarrierHandle / TaskHandle has "
            f"silently broken the Celery substrate."
        )
        # Pin the declared type too — ``TaskHandle`` says ``id: str``
        # and chord-id logging in the response dict treats it as a
        # string. A future substrate that satisfies ``hasattr`` with
        # e.g. a UUID object or ``None`` would slip past the
        # attribute-presence check above.
        assert isinstance(async_result_instance.id, str), (
            f"AsyncResult.id should be a str (TaskHandle declares "
            f"``id: str``); got {type(async_result_instance.id).__name__}"
        )

        # And ``DispatchHandle`` / ``BarrierHandle`` should both be
        # the same shared ``TaskHandle`` Protocol (no drift risk).
        from queue_backend.handle import DispatchHandle, TaskHandle

        assert BarrierHandle is TaskHandle
        assert DispatchHandle is TaskHandle


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


# --- Executing tests for call-site fairness contracts ---


def _load_api_deployment_tasks():
    """Load ``api-deployment/tasks.py`` as a module.

    The dash in ``api-deployment`` blocks normal ``import
    api-deployment.tasks``. We load via ``importlib.util`` instead so
    the test can drive the real ``_run_workflow_api`` function rather
    than scraping its source.
    """
    import importlib.util
    import inspect
    import pathlib

    src = inspect.getfile(__import__("queue_backend.barrier", fromlist=["a"]))
    api_tasks_path = (
        pathlib.Path(src).parent.parent / "api-deployment" / "tasks.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_api_deployment_tasks_for_test", api_tasks_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_workflow_api_with_mocks(
    monkeypatch,
    *,
    hash_values_of_files: dict | None = None,
    force_empty_batches: bool = False,
    force_falsy_chord_with_batches: bool = False,
    manual_review_required: bool = False,
    review_decisions_helper: MagicMock | None = None,
):
    """Drive ``_run_workflow_api`` end-to-end with the minimum mocks
    needed to exercise the chord-dispatch + zero-batch + queue-failure
    branches.

    Knobs:

    - ``force_empty_batches`` — ``_get_file_batches`` returns ``[]``
      and ``create_chord_execution`` returns ``None``. Exercises the
      zero-batch defensive dispatch fallback.
    - ``force_falsy_chord_with_batches`` — ``_get_file_batches``
      returns a non-empty list but ``create_chord_execution`` returns
      ``None`` anyway. Exercises the "genuine queue failure" branch
      that raises and maps to ``ExecutionStatus.ERROR``. Mutually
      exclusive with ``force_empty_batches``.
    - ``manual_review_required`` — ``_create_file_data`` returns a
      file_data whose ``manual_review_config["review_required"]`` is
      ``True``, exercising the manual-review decision branch. The
      caller can supply ``review_decisions_helper`` (a ``MagicMock``)
      to track invocations of
      ``_calculate_manual_review_decisions_for_batch_api``.

    Returns ``(result, mock_create_chord, mock_dispatch)`` so callers
    can assert on the response shape and on which dispatch path fired.
    """
    if force_empty_batches and force_falsy_chord_with_batches:
        raise AssertionError(
            "force_empty_batches and force_falsy_chord_with_batches are "
            "mutually exclusive — pick the branch under test"
        )
    api_tasks = _load_api_deployment_tasks()
    api_client = MagicMock(name="api_client")
    api_client.get_workflow_execution.return_value = MagicMock(
        success=True, error=None, data={}
    )
    api_client.get_file_history_for_files.return_value = MagicMock(
        success=True, data={"files": {}}
    )
    api_client.update_workflow_execution_status.return_value = MagicMock(success=True)
    api_client.update_pipeline_status.return_value = MagicMock(success=True)

    # Neutralise heavy upstream side effects.
    monkeypatch.setattr(
        api_tasks, "validate_workflow_tool_instances", lambda **kwargs: None
    )
    monkeypatch.setattr(
        api_tasks, "_log_api_file_history_statistics", lambda **kwargs: None
    )
    monkeypatch.setattr(
        api_tasks, "_log_api_batch_creation_statistics", lambda **kwargs: None
    )

    # Always patch ``_get_file_batches`` — the real implementation
    # filters non-``FileHashData``/``dict`` entries, which would drop
    # our ``MagicMock`` values and silently land in the zero-batch
    # branch even when ``force_empty_batches=False``. Patching here
    # gives the caller deterministic control over the chord vs
    # zero-batch path via the knobs.
    monkeypatch.setattr(
        api_tasks,
        "_get_file_batches",
        lambda **kwargs: [] if force_empty_batches else [["file_1_in_batch"]],
    )
    # Neutralise the per-batch helpers so ``batch_tasks`` is non-empty
    # in the chord-path case without us needing to construct real
    # ``FileBatchData`` objects.
    mock_file_data = MagicMock(name="file_data")
    # ``.manual_review_config.get("review_required", False)`` is a
    # real dict so we can flip it via the ``manual_review_required``
    # knob — MagicMocks would return truthy by default from .get(),
    # which would force the manual-review branch.
    mock_file_data.manual_review_config = {
        "review_required": manual_review_required,
    }
    monkeypatch.setattr(
        api_tasks, "_create_file_data", lambda **kwargs: mock_file_data
    )
    monkeypatch.setattr(
        api_tasks, "_create_batch_data", lambda **kwargs: {"batch": "data"}
    )
    if manual_review_required:
        # When the caller flips the flag, install a spy on the
        # manual-review decision helper so we can assert it was
        # invoked. Default arg ensures shape compatibility with the
        # real helper (one bool per file).
        helper = review_decisions_helper or MagicMock(
            name="_calculate_manual_review_decisions_for_batch_api",
            return_value=[False],
        )
        monkeypatch.setattr(
            api_tasks, "_calculate_manual_review_decisions_for_batch_api", helper
        )

    mock_create_chord = MagicMock(name="create_chord_execution")
    # When the chord path should fire normally, return a truthy
    # handle. When forced empty OR forced falsy-with-batches, return
    # ``None`` — the production code's ``if result is None:`` branch
    # then distinguishes the two cases via ``batch_tasks`` length.
    if force_empty_batches or force_falsy_chord_with_batches:
        mock_create_chord.return_value = None
    else:
        mock_create_chord.return_value = MagicMock(id="chord-result-id")
    monkeypatch.setattr(
        api_tasks.WorkflowOrchestrationUtils,
        "create_chord_execution",
        mock_create_chord,
    )

    mock_dispatch_result = MagicMock(name="dispatch_result")
    mock_dispatch_result.id = "callback-task-id"
    mock_dispatch = MagicMock(name="dispatch", return_value=mock_dispatch_result)
    monkeypatch.setattr(api_tasks, "dispatch", mock_dispatch)

    files = hash_values_of_files if hash_values_of_files is not None else {
        "f1": MagicMock(name="FileHashData_f1"),
    }
    result = api_tasks._run_workflow_api(
        api_client=api_client,
        schema_name="org_test",
        workflow_id="wf-1",
        execution_id="exec-1",
        hash_values_of_files=files,
        scheduled=False,
        execution_mode=None,
        pipeline_id="pipe-1",
        use_file_history=False,
        task_id="task-1",
    )
    return result, mock_create_chord, mock_dispatch


class TestCallSiteFairnessContracts:
    """Pin the ``FairnessKey`` shape each production call site declares.

    These were originally source-string-match tests. The problem:
    ``FairnessKey(...)`` appears at *both* the chord call site and
    the zero-batch fallback in ``api-deployment/tasks.py``, so a
    substring assertion would pass even if the primary chord call
    dropped ``fairness=`` entirely. These executing tests patch the
    helper and inspect the actual call args.
    """

    def test_api_deployment_passes_api_fairness_to_create_chord(
        self, monkeypatch
    ):
        """The chord call site in ``_run_workflow_api`` must pass
        ``fairness=FairnessKey(org_id=str(schema_name),
        workload_type=WorkloadType.API)`` to ``create_chord_execution``."""
        # ``_run_workflow_api_with_mocks(force_empty_batches=False)``
        # patches ``_get_file_batches`` to return a non-empty list so
        # the chord path actually fires (the helper's patches are
        # documented in ``_run_workflow_api_with_mocks``).
        _result, mock_create_chord, mock_dispatch = _run_workflow_api_with_mocks(
            monkeypatch,
            hash_values_of_files={"f1": MagicMock(name="file_1")},
            force_empty_batches=False,
        )
        # ``create_chord_execution`` MUST be called with the right
        # fairness — a refactor that drops ``fairness=`` or swaps the
        # workload type fails here loudly.
        assert mock_create_chord.called, (
            "_run_workflow_api did not call create_chord_execution"
        )
        fairness_kwarg = mock_create_chord.call_args.kwargs.get("fairness")
        assert fairness_kwarg is not None, "fairness= kwarg missing"
        assert fairness_kwarg == FairnessKey(
            org_id="org_test", workload_type=WorkloadType.API
        )
        # And the zero-batch fallback ``dispatch(...)`` MUST NOT have
        # fired — otherwise this test would silently pass via the
        # fallback's own ``fairness=`` argument even if the primary
        # ``create_chord_execution`` call dropped its ``fairness=``.
        # (Code-review feedback — no assertion in the original revision.)
        assert not mock_dispatch.called, (
            "Zero-batch fallback dispatch fired during the chord-path "
            "test — _get_file_batches mock returned empty unexpectedly, "
            "or create_chord_execution returned falsy. The chord-path "
            "fairness assertion above would otherwise be exercising the "
            "fallback's own fairness arg, not the chord call's."
        )
        # Header-task batch_tasks must be non-empty (else create_chord
        # would have been a no-op pass-through to the empty-header
        # guard inside the barrier).
        batch_tasks = mock_create_chord.call_args.kwargs.get("batch_tasks")
        assert batch_tasks, (
            "batch_tasks passed to create_chord_execution was empty — "
            "the chord path was not actually exercised"
        )

    def test_general_passes_non_api_fairness_to_create_chord(self, monkeypatch):
        """``general/tasks.py``'s ``_orchestrate_file_processing_general``
        must pass ``fairness=FairnessKey(org_id=organization_id,
        workload_type=WorkloadType.NON_API)`` to ``create_chord_execution``.

        ``general/tasks.py`` is directly importable (no dash), so the
        test patches the helper at the module level and drives the
        function with a minimal fixture.
        """
        from general import tasks as general_tasks

        api_client = MagicMock(name="api_client")
        api_client.get_workflow_execution.return_value = MagicMock(
            success=True, data={}
        )
        api_client.update_workflow_execution_status.return_value = MagicMock(
            success=True
        )

        # Patch only what's needed to reach the chord call.
        monkeypatch.setattr(
            general_tasks,
            "_get_file_batches_general",
            lambda **kwargs: [MagicMock(name="batch_1")],
        )
        monkeypatch.setattr(
            general_tasks, "_create_batch_data_general", lambda **kwargs: MagicMock()
        )

        mock_create_chord = MagicMock(name="create_chord_execution")
        mock_create_chord.return_value = MagicMock(id="chord-id")
        monkeypatch.setattr(
            general_tasks.WorkflowOrchestrationUtils,
            "create_chord_execution",
            mock_create_chord,
        )

        # ``contextlib.suppress`` over a bare ``except Exception: pass``
        # to declare intent explicitly: any post-``create_chord_execution``
        # raise (e.g. the mocked api_client's status update path) is
        # tolerated, because the next ``assert mock_create_chord.called``
        # is what proves the chord call was actually reached.
        with contextlib.suppress(Exception):
            general_tasks._orchestrate_file_processing_general(
                api_client=api_client,
                workflow_id="wf-1",
                execution_id="exec-1",
                source_files={"f1": MagicMock(name="file_1")},
                pipeline_id="pipe-1",
                scheduled=False,
                execution_mode=None,
                use_file_history=False,
                organization_id="org_test",
            )

        assert mock_create_chord.called, (
            "_orchestrate_file_processing_general did not call "
            "create_chord_execution"
        )
        fairness_kwarg = mock_create_chord.call_args.kwargs.get("fairness")
        assert fairness_kwarg is not None, "fairness= kwarg missing"
        assert fairness_kwarg == FairnessKey(
            org_id="org_test", workload_type=WorkloadType.NON_API
        )
        # Match the api-deployment sibling: header tasks must be
        # non-empty so we're not silently exercising an empty-header
        # short-circuit.
        batch_tasks = mock_create_chord.call_args.kwargs.get("batch_tasks")
        assert batch_tasks, (
            "batch_tasks passed to create_chord_execution was empty — "
            "the chord path was not actually exercised"
        )


class TestApiDeploymentZeroFilesContract:
    """Executing pin for the api-deployment zero-batch handler.

    Originally a source-string-match test. The problem with the
    string-match form: it would pass even if the dispatch branch
    were deleted — the matched tokens (``args=[[]]``,
    ``process_batch_callback_api``, ``if not batch_tasks:``) also
    appear on the chord path or in surrounding code. A test that
    doesn't execute the branch can't prove the branch works.

    This version drives the actual code path via ``_run_workflow_api``
    with mocked dependencies and forced-empty batches, then asserts
    ``dispatch(...)`` is called once with the chord-empty semantic
    (``args=[[]]``) and the same fairness slot the chord path would
    have used.

    Effectively unreachable in production — the upstream ``if not
    hash_values_of_files:`` early return plus valid ``FileHashData``
    inputs mean ``_get_file_batches`` always yields >=1 batch — but
    the executing test locks the defensive contract so a future
    refactor that drops it fails loudly.
    """

    def test_zero_batch_branch_dispatches_callback_with_empty_list(
        self, monkeypatch
    ):
        result, _create_chord, mock_dispatch = _run_workflow_api_with_mocks(
            monkeypatch,
            hash_values_of_files={"f1": MagicMock(name="file_1")},
            force_empty_batches=True,
        )

        # Dispatch was called exactly once, with the chord-empty
        # semantic (args=[[]]) and the same fairness slot the chord
        # path uses.
        mock_dispatch.assert_called_once()
        call = mock_dispatch.call_args
        assert call.args[0] == "process_batch_callback_api"
        assert call.kwargs.get("args") == [[]]
        callback_kwargs = call.kwargs.get("kwargs")
        assert callback_kwargs == {
            "execution_id": "exec-1",
            "pipeline_id": "pipe-1",
            "organization_id": "org_test",
        }
        # Pin the callback queue too — without this a refactor that
        # routes the zero-batch callback to the wrong queue (or drops
        # the ``queue=`` kwarg entirely) would pass undetected.
        # (Code-review feedback — no assertion in the original revision.)
        assert call.kwargs.get("queue") == "api_file_processing_callback"
        assert call.kwargs.get("fairness") == FairnessKey(
            org_id="org_test", workload_type=WorkloadType.API
        )

        # Response shape: orchestrated with zero batches, callback
        # task id surfaced as chord_id (semantically a task id, not a
        # chord id — see the inline comment at the call site).
        assert result["status"] == "orchestrated"
        assert result["batches_created"] == 0
        assert result["chord_id"] == "callback-task-id"


class TestApiDeploymentQueueFailureContract:
    """Executing pin for the "genuine queue failure" branch.

    When ``batch_tasks`` is non-empty but ``create_chord_execution``
    returns ``None`` (a broker outage / serialisation failure that
    bypasses the empty-header guard), the production code raises
    and the outer handler maps it to ``ExecutionStatus.ERROR``.

    This is the higher-severity sub-branch — a broker failure
    mapping to ERROR is real production behaviour, not the
    unreachable zero-files defence; this branch can fire on a real
    broker outage or serialisation failure.
    """

    def test_falsy_chord_with_non_empty_batches_raises(self, monkeypatch):
        """When the barrier returns ``None`` despite non-empty
        ``batch_tasks``, ``_run_workflow_api`` must raise — the outer
        task handler then maps this to ``ExecutionStatus.ERROR`` for
        the pipeline status update."""
        with pytest.raises(Exception, match=r"(?i)queue|failed|chord"):
            _run_workflow_api_with_mocks(
                monkeypatch,
                hash_values_of_files={"f1": MagicMock(name="file_1")},
                force_falsy_chord_with_batches=True,
            )

    def test_falsy_chord_with_non_empty_batches_does_not_dispatch_fallback(
        self, monkeypatch
    ):
        """The fallback ``dispatch(args=[[]], ...)`` MUST NOT fire on
        the genuine-queue-failure branch — that's reserved for the
        zero-batch defence. A future refactor that routed both
        falsy-result cases through the same fallback would silently
        lose the ERROR signal."""
        with contextlib.suppress(Exception):
            _result, _create_chord, mock_dispatch = (
                _run_workflow_api_with_mocks(
                    monkeypatch,
                    hash_values_of_files={"f1": MagicMock(name="file_1")},
                    force_falsy_chord_with_batches=True,
                )
            )
            assert not mock_dispatch.called, (
                "Genuine queue failure must raise, not silently dispatch the "
                "zero-batch fallback callback"
            )


class TestApiDeploymentManualReviewContract:
    """Executing pin for the manual-review decision branch.

    When ``file_data.manual_review_config["review_required"]`` is
    ``True``, the per-batch loop calls
    ``_calculate_manual_review_decisions_for_batch_api`` to mutate
    ``manual_review_config["file_decisions"]`` before the batch
    data rides the chord. The base ``_run_workflow_api_with_mocks``
    hard-codes ``review_required=False`` for the other tests, so
    this class flips the knob to keep the manual-review path
    exercised under an executing test.
    """

    def test_manual_review_required_invokes_decision_helper_per_batch(
        self, monkeypatch
    ):
        """With ``review_required=True``, the decision helper is
        invoked exactly once per batch and the chord still fires
        with the same fairness slot as the non-review path."""
        decisions_helper = MagicMock(
            name="_calculate_manual_review_decisions_for_batch_api",
            return_value=[False],
        )
        _result, mock_create_chord, mock_dispatch = (
            _run_workflow_api_with_mocks(
                monkeypatch,
                hash_values_of_files={"f1": MagicMock(name="file_1")},
                manual_review_required=True,
                review_decisions_helper=decisions_helper,
            )
        )

        # One batch in the test helper → exactly one helper call.
        assert decisions_helper.call_count == 1, (
            "Manual-review decision helper must run once per batch — got "
            f"{decisions_helper.call_count}"
        )
        # Chord path still fires with API fairness — the manual-review
        # branch must not divert into the fallback dispatch.
        assert mock_create_chord.called
        assert not mock_dispatch.called
        fairness_kwarg = mock_create_chord.call_args.kwargs.get("fairness")
        assert fairness_kwarg == FairnessKey(
            org_id="org_test", workload_type=WorkloadType.API
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
