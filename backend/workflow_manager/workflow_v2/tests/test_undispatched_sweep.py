"""PENDING is not terminal — an undispatched execution must not stay that way.

Guards the sweep that closes the create-then-dispatch window (see the module
docstring). The two failure modes that matter are opposite in direction, and both are
pinned here:

  * FAILING TO SWEEP leaves an execution that can never reach COMPLETED or ERROR —
    invisible failure. 967 of them appeared from one 5-minute load test.
  * SWEEPING TOO EAGERLY marks a LIVE execution ERROR. Far worse, so the young-row,
    dispatched-row and raced-row cases are asserted explicitly rather than assumed.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from unstract.core.data_models import ExecutionStatus

# NOT module-level: TestUserFacingMessage asserts a pure string contract and needs
# no database, so it must stay in the UNIT tier. conftest auto-marks django_db
# tests as `integration`, which the unit lane excludes — a module-level marker
# would have hidden the message assertions behind live Postgres for no reason.


def _execution(**overrides):
    """A PENDING, never-dispatched execution old enough to sweep.

    A workflow is REQUIRED, not incidental: ``WorkflowExecution.save()`` calls
    ``_handle_execution_cache()``, which dereferences ``self.workflow.id``. Built
    without one, every test here died with ``AttributeError: 'NoneType' object has no
    attribute 'id'`` before reaching its assertion — which is what CI reported the
    moment this PR left draft and the integration tier actually ran.
    """
    from workflow_manager.workflow_v2.models import Workflow, WorkflowExecution

    fields = {
        "id": uuid.uuid4(),
        "workflow": Workflow.objects.create(
            workflow_name=f"wf-sweep-{uuid.uuid4().hex[:8]}"
        ),
        "status": ExecutionStatus.PENDING.value,
        "task_id": None,
        "queue_message_id": None,
    }
    fields.update(overrides)
    created_at = fields.pop("created_at", timezone.now() - timedelta(hours=2))
    ex = WorkflowExecution.objects.create(**fields)
    # created_at is auto_now_add; bypass it with a direct UPDATE so age is controllable.
    WorkflowExecution.objects.filter(id=ex.id).update(created_at=created_at)
    ex.refresh_from_db()
    return ex


@pytest.mark.django_db
class TestSweepsWhatNothingElseOwns:
    def test_an_aged_undispatched_execution_is_marked_error(self):
        from workflow_manager.workflow_v2.models import WorkflowExecution
        from workflow_manager.workflow_v2.undispatched_sweep import (
            UNDISPATCHED_ERROR_MESSAGE,
            sweep_undispatched_executions,
        )

        ex = _execution()
        assert sweep_undispatched_executions() == 1

        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.ERROR.value
        assert ex.error_message == UNDISPATCHED_ERROR_MESSAGE
        assert (
            WorkflowExecution.objects.filter(status=ExecutionStatus.PENDING.value).count()
            == 0
        )

    def test_it_is_idempotent(self):
        """Runs on every tick — a second pass must find nothing, not re-write."""
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        _execution()
        assert sweep_undispatched_executions() == 1
        assert sweep_undispatched_executions() == 0


@pytest.mark.django_db
class TestNeverTouchesALiveExecution:
    """The dangerous direction. Each case is a way a live run could be killed."""

    def test_a_young_execution_is_left_alone(self):
        """Dispatch follows creation within seconds; age is the only separator."""
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution(created_at=timezone.now() - timedelta(seconds=30))
        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.PENDING.value

    def test_a_pg_dispatched_execution_is_left_alone(self):
        """queue_message_id set => the PG queue holds it; the reaper owns it now."""
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution(queue_message_id=4242)
        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.PENDING.value

    def test_a_celery_dispatched_execution_is_left_alone(self):
        """task_id set => Celery holds it. The window is upstream of
        resolve_transport, so the predicate must be transport-aware or a flag-off
        deployment would have its live executions terminalised.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution(task_id=uuid.uuid4())
        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.PENDING.value

    @pytest.mark.parametrize(
        "status",
        [
            ExecutionStatus.EXECUTING.value,
            ExecutionStatus.COMPLETED.value,
            ExecutionStatus.ERROR.value,
            ExecutionStatus.STOPPED.value,
        ],
    )
    def test_only_pending_is_swept(self, status):
        """EXECUTING is running; the terminal three are already resolved. Rewriting
        a COMPLETED run's error_message would be corruption, not recovery.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution(status=status)
        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == status
        assert ex.error_message == ""

    def test_a_row_dispatched_mid_sweep_is_not_clobbered(self):
        """The read-then-write race, which is why the UPDATE re-carries the predicate.

        Simulates dispatch landing between candidate selection and the write: the
        row is passed in as a candidate id but no longer matches, so Postgres skips
        it. A plain `filter(id__in=ids).update(...)` would mark a live run ERROR.
        """
        from workflow_manager.workflow_v2.models import WorkflowExecution
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution()
        WorkflowExecution.objects.filter(id=ex.id).update(queue_message_id=99)

        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.PENDING.value


@pytest.mark.django_db
class TestDispatchIsAPositiveFactNotAnInference:
    """The fix for the defect the whole file's caution was working around.

    The sweep used to infer "never dispatched" from `task_id IS NULL AND
    queue_message_id IS NULL`. Three paths in workflow_helper reach that state on a
    RUNNING execution — a swallowed exception around _record_dispatch_handle, an empty
    handle, an unparseable PG handle — so the sweep could mark live work ERROR and, on
    the PG transport, get it silently DROPPED (both worker entry points stop on a
    terminal execution rather than superseding it).

    `dispatched_at` is stamped the instant dispatch succeeds, upstream of all three.
    """

    def test_a_dispatched_row_is_never_swept_even_with_no_handles(self):
        """THE regression. This is exactly the shape the three failure paths produce:
        dispatch succeeded, neither handle was recorded. Before dispatched_at this row
        was swept to ERROR while its worker was still running.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution(dispatched_at=timezone.now() - timedelta(hours=2))
        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.PENDING.value

    def test_an_unstamped_row_with_a_handle_is_still_not_swept(self):
        """The single-phase rollout guarantee. During a rolling deploy an OLD backend
        pod dispatches without stamping, so the row has no dispatched_at — but it does
        have a handle. Keeping the handle checks alongside the new one is what lets this
        ship in one release instead of two.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution(task_id=uuid.uuid4())
        assert sweep_undispatched_executions() == 0
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.PENDING.value

    def test_a_genuinely_undispatched_row_is_still_swept(self):
        """The fix must not disable the sweep. A row with no stamp and no handle is the
        967-orphan case this exists for, and it must still terminalise.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            sweep_undispatched_executions,
        )

        ex = _execution()
        assert sweep_undispatched_executions() == 1
        ex.refresh_from_db()
        assert ex.status == ExecutionStatus.ERROR.value


class TestGracePeriodIsSizedForTheQueue:
    """The grace period is the ONLY thing separating "abandoned" from "dispatched but
    not yet recorded", and on PG that distinction has teeth.

    A row this sweep terminalises while its message is still queued does not get run
    late — both PG worker entry points STOP on a terminal execution and ack the message
    (general/tasks.py returns skipped_terminal_execution; file_processing/tasks.py
    raises _TerminalExecutionSkip), so the work is dropped. On Celery the orchestrator
    ran regardless and its own terminal write superseded the ERROR, which is why this
    was survivable before the PG transport and is not after it.

    An hour is chosen to sit clear of any realistic dequeue latency. Lowering it back
    toward the queue's p99 wait re-opens that window, so this pins the value: change it
    deliberately, with a latency figure in hand, not as a tidy-up.
    """

    def test_the_grace_period_is_an_hour(self):
        from workflow_manager.workflow_v2.undispatched_sweep import (
            DEFAULT_MIN_AGE_SECONDS,
        )

        assert DEFAULT_MIN_AGE_SECONDS == 3600

    def test_it_stays_clear_of_the_barrier_stuck_timeout(self):
        """Must remain well under ~2.5h or this sweep and the barrier reaper start
        contending for the same rows — the disjointness the two sweeps depend on.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            DEFAULT_MIN_AGE_SECONDS,
        )

        assert DEFAULT_MIN_AGE_SECONDS < 9000


class TestNeverDeletesStagedInput:
    """The sweep must not perform any IRREVERSIBLE cleanup, because its "never
    dispatched" test is an INFERENCE and the inference is unsound.

    Both handles being NULL is reached by three paths in ``workflow_helper`` AFTER the
    message is on its transport: ``_record_dispatch_handle`` raising and being swallowed
    by the caller ("continuing — the orchestrator is already running"), an empty handle
    returning early, and a PG handle that will not parse returning early. So a claimed
    row may be a LIVE execution.

    Marking it ERROR is survivable — the running worker's own terminal write supersedes
    it, and error→completed is explicitly permitted by the status guard. Deleting its
    staged input is not: the worker is still going to read it.

    This pins the ABSENCE of that call. Re-adding it is only safe once dispatch is a
    positive fact (a stamped ``dispatched_at``) rather than an inferred absence.
    """

    def test_the_sweep_module_does_not_delete_api_storage(self):
        import inspect

        from workflow_manager.workflow_v2 import undispatched_sweep

        source = inspect.getsource(undispatched_sweep)
        executable = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        assert "delete_api_storage_dir" not in executable

    def test_releasing_resources_still_frees_the_rate_limit_slot(self):
        """The reversible half must survive the removal — a held slot consumes the
        org's API-deployment concurrency budget until the limiter TTL expires it.
        """
        import inspect

        from workflow_manager.workflow_v2 import undispatched_sweep

        source = inspect.getsource(undispatched_sweep._release_abandoned_resources)
        assert "release_slot" in source


class TestUserFacingMessage:
    """`error_message` is rendered in the UI — ExecutionSerializer uses `exclude`,
    not `fields`, so every unlisted model field is serialized to customers.
    """

    def test_it_fits_the_column_with_the_ref_intact(self):
        """CharField(max_length=256) truncates silently, which would eat the trailing
        ref code and leave support without the greppable handle.
        """
        from workflow_manager.workflow_v2.models.execution import (
            EXECUTION_ERROR_LENGTH,
        )
        from workflow_manager.workflow_v2.undispatched_sweep import (
            UNDISPATCHED_ERROR_MESSAGE,
        )

        assert len(UNDISPATCHED_ERROR_MESSAGE) <= EXECUTION_ERROR_LENGTH
        assert UNDISPATCHED_ERROR_MESSAGE.rstrip().endswith("(ref: EXEC_NOT_STARTED)")

    def test_it_names_no_internals(self):
        """A customer reading this must not meet our vocabulary. The existing reaper
        strings ("the final aggregating callback never fired before the barrier
        expired") are the anti-pattern this guards against.
        """
        from workflow_manager.workflow_v2.undispatched_sweep import (
            UNDISPATCHED_ERROR_MESSAGE,
        )

        leaked = [
            w
            for w in (
                "queue",
                "barrier",
                "dispatch",
                "gateway",
                "celery",
                "worker",
                "reaper",
                "502",
                "null",
            )
            if w in UNDISPATCHED_ERROR_MESSAGE.lower()
        ]
        assert not leaked, f"internal term(s) in a user-facing message: {leaked}"

    def test_it_answers_what_the_user_needs(self):
        """Did anything run, is my data affected, what do I do."""
        from workflow_manager.workflow_v2.undispatched_sweep import (
            UNDISPATCHED_ERROR_MESSAGE,
        )

        low = UNDISPATCHED_ERROR_MESSAGE.lower()
        assert "did not start" in low
        assert "no files were processed" in low
        assert "run it again" in low
