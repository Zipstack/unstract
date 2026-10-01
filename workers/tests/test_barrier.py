"""Tests for the ``Barrier`` seam and its two production fan-out call sites.

The seam exists because ``WorkflowOrchestrationUtils.create_chord_execution`` and
``api-deployment/tasks.py`` both fan out and both need one dispatch point. It
once carried three implementations selected by ``WORKER_BARRIER_BACKEND``;
UN-4078 left only :class:`PgBarrier`.

Two layers of coverage:

1. **Protocol shape** — the surviving implementation satisfies ``Barrier``, and
   the handle satisfies ``BarrierHandle``.
2. **Call-site contracts** — the api-deployment fan-out passes API fairness,
   handles the zero-batch branch, raises rather than silently falling back on a
   falsy result with non-empty batches, and routes manual review per batch.

The wire-equivalence layer (chord call shape, AMQP fairness headers) went with
``CeleryChordBarrier``; the equivalent PG assertions live in
``test_pg_barrier.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from queue_backend import (
    Barrier,
    BarrierHandle,
    FairnessKey,
)
from queue_backend.fairness import WorkloadType


@pytest.fixture
def app() -> MagicMock:
    """Celery-app-shaped mock with a working ``.signature(...)``.

    The fan-out call sites still build header signatures through a Celery app
    before handing them to the barrier, so they still need one.
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
    def test_pg_barrier_satisfies_protocol(self):
        """The one remaining implementation is structurally a ``Barrier``.

        Kept after ``CeleryChordBarrier`` was deleted: the Protocol still exists
        because two call sites program against it, so something must assert the
        implementation actually satisfies it.
        """
        from queue_backend import PgBarrier

        barrier: Barrier = PgBarrier()
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
        from celery import Celery
        from celery.result import AsyncResult

        # Assert against a real ``AsyncResult`` *instance* — that's
        # what every production call site receives and logs ``.id``
        # from. We don't rely on whether the attribute is class-level,
        # a property, or set in ``__init__``; the instance check is
        # the smallest-blast-radius equivalent of "production sees
        # this object and reads ``.id``".
        #
        # Bind to an explicit backend-less probe app (not the ambient
        # ``current_app``): whichever worker app happens to be current in a
        # full-suite run may carry a real ``db+postgresql://`` result backend,
        # and binding ``AsyncResult`` to it would try to connect. ``.id`` is the
        # constructor argument and needs no backend, so this stays a pure
        # protocol-shape check.
        probe_app = Celery("barrier-protocol-probe", set_as_current=False)
        #
        # ``required_attrs`` is hand-maintained: if a future refactor
        # adds a required attribute to ``TaskHandle`` /
        # ``BarrierHandle``, add it here too. The hand-maintained form
        # is grepable next to the comment that explains it, and
        # ``TaskHandle`` is intentionally minimal (``id: str``) so the
        # manual-update burden is one line every several phases.
        # ``__annotations__`` introspection would also work (and
        # doesn't require ``@runtime_checkable``), but the explicit
        # tuple keeps the contract surface explicit.
        async_result_instance = AsyncResult("placeholder-task-id", app=probe_app)
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


class TestCreateChordExecutionUsesPgBarrier:
    """Pin ``WorkflowOrchestrationUtils.create_chord_execution`` to :class:`PgBarrier`.

    Replaces the old singleton-routing suite. There used to be a module-level
    ``_BARRIER`` chosen by ``WORKER_BARRIER_BACKEND`` plus a per-execution
    ``transport`` that decided between it and a fresh ``PgBarrier``; both went
    with the Celery transport (UN-4078). What is worth pinning now is that the
    call site still funnels through one substrate and forwards its arguments
    unchanged — a refactor that reached for a barrier directly, or dropped
    ``fairness`` on the way through, would otherwise pass silently.
    """

    def test_delegates_to_pg_barrier_with_arguments_intact(self):
        from shared.workflow.execution import orchestration_utils
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        app_mock = MagicMock(name="celery_app")
        batch = [MagicMock(name="h1")]
        fairness = FairnessKey(org_id="org-1", workload_type=WorkloadType.API)

        with patch.object(orchestration_utils, "PgBarrier") as barrier_cls:
            barrier_cls.return_value.enqueue.return_value = MagicMock(name="result")
            WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=batch,
                callback_task_name="process_batch_callback_api",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="api_file_processing_callback",
                app_instance=app_mock,
                fairness=fairness,
            )

        barrier_cls.return_value.enqueue.assert_called_once_with(
            batch,
            callback_task_name="process_batch_callback_api",
            callback_kwargs={"execution_id": "exec-1"},
            callback_queue="api_file_processing_callback",
            app_instance=app_mock,
            fairness=fairness,
        )

    def test_no_transport_argument_is_accepted(self):
        """The per-execution ``transport`` kwarg is gone, not merely ignored.

        It was the field that let a stale payload select a Celery fan-out after
        the Celery consumers were scaled to zero. Accepting and discarding it
        would leave that call shape looking valid.
        """
        from shared.workflow.execution.orchestration_utils import (
            WorkflowOrchestrationUtils,
        )

        with pytest.raises(TypeError):
            WorkflowOrchestrationUtils.create_chord_execution(
                batch_tasks=[MagicMock()],
                callback_task_name="cb",
                callback_kwargs={"execution_id": "exec-1"},
                callback_queue="q",
                app_instance=MagicMock(),
                transport="celery",
            )


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


@dataclass
class _WorkflowApiMocks:
    """Spy bundle from ``_setup_workflow_api_mocks``.

    All attributes are bound *before* the production function runs,
    so a test asserting on spies after a raising call (e.g. the
    queue-failure branch) can still inspect them.
    """

    api_tasks: object
    api_client: MagicMock
    create_chord: MagicMock
    dispatch: MagicMock
    decisions_helper: MagicMock


# Three production branches under test, one knob. Replacing
# ``force_empty_batches`` + ``force_falsy_chord_with_batches`` (two
# bools encoding three states with a runtime mutual-exclusivity
# guard) — the illegal ``(True, True)`` combination is now
# unrepresentable.
_VALID_CHORD_OUTCOMES = ("success", "empty_batches", "queue_failure")


def _setup_workflow_api_mocks(
    monkeypatch,
    *,
    chord_outcome: str = "success",
    manual_review_required: bool = False,
    num_batches: int = 1,
) -> _WorkflowApiMocks:
    """Setup mocks; caller drives ``_run_workflow_api``.

    Use this when the test needs to assert on spies *after* the
    production function raises (e.g. the queue-failure branch).
    Tests that don't need post-raise assertions can use the thin
    convenience wrapper ``_run_workflow_api_with_mocks``.

    ``chord_outcome`` controls which production branch fires:

    - ``"success"`` — non-empty batches, truthy chord handle. Normal
      chord path completes.
    - ``"empty_batches"`` — ``_get_file_batches`` yields ``[]``,
      chord returns ``None``. Zero-batch defensive dispatch fires.
    - ``"queue_failure"`` — ``_get_file_batches`` yields non-empty
      batches, chord returns ``None`` anyway. Production raises so
      the outer handler can map to ``ExecutionStatus.ERROR``.

    ``num_batches`` controls how many batches ``_get_file_batches``
    returns when ``chord_outcome != "empty_batches"`` — set >1 to
    exercise per-batch multiplicity contracts (e.g. the manual-
    review decision helper is invoked once per batch).
    """
    if chord_outcome not in _VALID_CHORD_OUTCOMES:
        raise AssertionError(
            f"chord_outcome must be one of {_VALID_CHORD_OUTCOMES}, "
            f"got {chord_outcome!r}"
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

    # ``_get_file_batches`` always patched — the real implementation
    # filters non-``FileHashData``/``dict`` entries, which would drop
    # ``MagicMock`` values and silently route into the zero-batch
    # branch. Patching here gives the caller deterministic control
    # over both the branch under test and the batch count.
    if chord_outcome == "empty_batches":
        batches_to_return: list[list[str]] = []
    else:
        batches_to_return = [
            [f"file_in_batch_{i}"] for i in range(num_batches)
        ]
    monkeypatch.setattr(
        api_tasks, "_get_file_batches", lambda **kwargs: batches_to_return
    )

    # Neutralise the per-batch helpers so ``batch_tasks`` is non-empty
    # without constructing real ``FileBatchData`` objects.
    mock_file_data = MagicMock(name="file_data")
    # Real dict (not MagicMock) so ``.get("review_required", False)``
    # returns the requested bool — MagicMocks would return truthy by
    # default from ``.get()``, forcing the manual-review branch.
    mock_file_data.manual_review_config = {
        "review_required": manual_review_required,
    }
    monkeypatch.setattr(
        api_tasks, "_create_file_data", lambda **kwargs: mock_file_data
    )
    monkeypatch.setattr(
        api_tasks, "_create_batch_data", lambda **kwargs: {"batch": "data"}
    )
    # Always create the decisions-helper spy and install it; tests
    # that don't flip ``manual_review_required`` simply never see it
    # invoked. Exposing it on the spy bundle removes the previous
    # caller-supplied/fallback dead branch.
    decisions_helper = MagicMock(
        name="_calculate_manual_review_decisions_for_batch_api",
        return_value=[False],
    )
    if manual_review_required:
        monkeypatch.setattr(
            api_tasks,
            "_calculate_manual_review_decisions_for_batch_api",
            decisions_helper,
        )

    mock_create_chord = MagicMock(name="create_chord_execution")
    # Truthy handle on the success path; ``None`` on the two failure
    # paths. Production's ``if result is None:`` branch then
    # distinguishes the two cases via ``batch_tasks`` length.
    if chord_outcome == "success":
        mock_create_chord.return_value = MagicMock(id="chord-result-id")
    else:
        mock_create_chord.return_value = None
    monkeypatch.setattr(
        api_tasks.WorkflowOrchestrationUtils,
        "create_chord_execution",
        mock_create_chord,
    )

    mock_dispatch_result = MagicMock(name="dispatch_result")
    mock_dispatch_result.id = "callback-task-id"
    mock_dispatch = MagicMock(name="dispatch", return_value=mock_dispatch_result)
    monkeypatch.setattr(api_tasks, "dispatch", mock_dispatch)

    return _WorkflowApiMocks(
        api_tasks=api_tasks,
        api_client=api_client,
        create_chord=mock_create_chord,
        dispatch=mock_dispatch,
        decisions_helper=decisions_helper,
    )


def _run_workflow_api_with_mocks(
    monkeypatch,
    *,
    hash_values_of_files: dict | None = None,
    chord_outcome: str = "success",
    manual_review_required: bool = False,
    num_batches: int = 1,
):
    """Convenience wrapper around ``_setup_workflow_api_mocks``.

    Setup + run; returns ``(result, create_chord, dispatch)`` for
    tests where ``_run_workflow_api`` doesn't raise. Tests that need
    to assert on spies after a raising call should use
    ``_setup_workflow_api_mocks`` directly so the spies are bound
    before the raise.
    """
    mocks = _setup_workflow_api_mocks(
        monkeypatch,
        chord_outcome=chord_outcome,
        manual_review_required=manual_review_required,
        num_batches=num_batches,
    )
    files = hash_values_of_files if hash_values_of_files is not None else {
        "f1": MagicMock(name="FileHashData_f1"),
    }
    result = mocks.api_tasks._run_workflow_api(
        api_client=mocks.api_client,
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
    return result, mocks.create_chord, mocks.dispatch


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
        # ``chord_outcome="success"`` patches ``_get_file_batches``
        # to return a non-empty list and ``create_chord_execution``
        # to return a truthy handle so the chord path actually fires
        # (helper patches documented in ``_setup_workflow_api_mocks``).
        _result, mock_create_chord, mock_dispatch = _run_workflow_api_with_mocks(
            monkeypatch,
            hash_values_of_files={"f1": MagicMock(name="file_1")},
            chord_outcome="success",
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

        # Tolerate post-``create_chord_execution`` raises (e.g. the
        # mocked api_client's status-update path), but re-raise if
        # ``create_chord_execution`` was never invoked — a pre-chord
        # regression would otherwise be silently swallowed and surface
        # as a misleading ``assert mock_create_chord.called`` failure
        # rather than the actual error.
        try:
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
        except Exception:
            if not mock_create_chord.called:
                raise

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
            chord_outcome="empty_batches",
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
        # Pin the exact production message rather than a loose
        # ``queue|failed|chord`` regex — the loose form would also
        # match a misconfigured-harness ``AssertionError`` or any
        # setup error whose message contains "failed", masking a
        # harness misconfiguration as a passing assertion.
        mocks = _setup_workflow_api_mocks(
            monkeypatch, chord_outcome="queue_failure"
        )
        with pytest.raises(Exception, match=r"Failed to queue execution task exec-1"):
            mocks.api_tasks._run_workflow_api(
                api_client=mocks.api_client,
                schema_name="org_test",
                workflow_id="wf-1",
                execution_id="exec-1",
                hash_values_of_files={"f1": MagicMock(name="file_1")},
                scheduled=False,
                execution_mode=None,
                pipeline_id="pipe-1",
                use_file_history=False,
                task_id="task-1",
            )

    def test_falsy_chord_with_non_empty_batches_does_not_dispatch_fallback(
        self, monkeypatch
    ):
        """The fallback ``dispatch(args=[[]], ...)`` MUST NOT fire on
        the genuine-queue-failure branch — that's reserved for the
        zero-batch defence. A future refactor that routed both
        falsy-result cases through the same fallback would silently
        lose the ERROR signal.

        Previous revision had this assertion inside
        ``contextlib.suppress(Exception)`` and bound ``mock_dispatch``
        from the function's tuple return — which never executed because
        the production code raised before the return. ``AssertionError``
        is an ``Exception`` so the suppress would have swallowed any
        failing assert too. Both defects fixed by:

        1. Setting up mocks via ``_setup_workflow_api_mocks`` so spies
           are bound *before* ``_run_workflow_api`` runs.
        2. Asserting on ``mocks.dispatch.called`` *outside* the
           ``pytest.raises`` block so an assertion failure surfaces.
        """
        mocks = _setup_workflow_api_mocks(
            monkeypatch, chord_outcome="queue_failure"
        )
        with pytest.raises(Exception, match=r"Failed to queue execution task exec-1"):
            mocks.api_tasks._run_workflow_api(
                api_client=mocks.api_client,
                schema_name="org_test",
                workflow_id="wf-1",
                execution_id="exec-1",
                hash_values_of_files={"f1": MagicMock(name="file_1")},
                scheduled=False,
                execution_mode=None,
                pipeline_id="pipe-1",
                use_file_history=False,
                task_id="task-1",
            )
        # The fallback dispatch was monkeypatched on the module and
        # survives the raise; assert outside the ``pytest.raises``
        # block so an assertion failure isn't swallowed.
        assert not mocks.dispatch.called, (
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
        with the same fairness slot as the non-review path.

        Drives the helper with ``num_batches=3`` so the "once per
        batch" contract is genuinely exercised — a regression
        invoking the helper 0× or 2× per batch wouldn't be caught
        with only one batch."""
        num_batches = 3
        mocks = _setup_workflow_api_mocks(
            monkeypatch,
            chord_outcome="success",
            manual_review_required=True,
            num_batches=num_batches,
        )
        mocks.api_tasks._run_workflow_api(
            api_client=mocks.api_client,
            schema_name="org_test",
            workflow_id="wf-1",
            execution_id="exec-1",
            hash_values_of_files={"f1": MagicMock(name="file_1")},
            scheduled=False,
            execution_mode=None,
            pipeline_id="pipe-1",
            use_file_history=False,
            task_id="task-1",
        )

        # N batches → exactly N helper calls.
        assert mocks.decisions_helper.call_count == num_batches, (
            f"Manual-review decision helper must run once per batch — "
            f"got {mocks.decisions_helper.call_count}, "
            f"expected {num_batches}"
        )
        # Chord path still fires with API fairness — the manual-review
        # branch must not divert into the fallback dispatch.
        assert mocks.create_chord.called
        assert not mocks.dispatch.called
        fairness_kwarg = mocks.create_chord.call_args.kwargs.get("fairness")
        assert fairness_kwarg == FairnessKey(
            org_id="org_test", workload_type=WorkloadType.API
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
