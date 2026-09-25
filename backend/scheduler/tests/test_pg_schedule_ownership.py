"""Unit tests for the schedule-ownership ramp control (Phase 9, ②c).

DB-free: Flipt and the ORM (``PgPeriodicSchedule`` / ``PeriodicTask``) are mocked.
These pin the fail-closed rollout decision and — the load-bearing property — that
handing a schedule to PG disables its Beat ``PeriodicTask`` in the same step (no
double-fire), with pause state preserved.
"""

import contextlib
from unittest.mock import MagicMock, patch

import pytest

from scheduler import ownership

_PID = "11111111-1111-1111-1111-111111111111"
_ORG = "org_abc"


class TestResolveScheduleOwner:
    """Ownership is gated solely by PG_SCHEDULER_ENABLED (UN-4046).

    The ``pg_queue_enabled`` Flipt cases (unavailable / true / false / error) are
    gone with the flag. The env gate still has to hold in both directions:
    ``reconcile_ownership_for`` disables the Beat PeriodicTask whenever this says
    PG, so a deployment without a running PG scheduler must be able to keep Beat.
    """

    def test_defaults_to_pg(self, monkeypatch):
        monkeypatch.delenv("PG_SCHEDULER_ENABLED", raising=False)
        assert ownership.resolve_schedule_owner() is True

    def test_env_gate_off_keeps_beat(self, monkeypatch):
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        assert ownership.resolve_schedule_owner() is False

    def test_env_gate_on_is_pg(self, monkeypatch):
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "true")
        assert ownership.resolve_schedule_owner() is True


class TestReconcileOwnership:
    @pytest.fixture(autouse=True)
    def _scheduler_gate_on(self, monkeypatch):
        """These pin the FINAL-phase behaviour, when hand-over is switched on.

        PG_SCHEDULER_ENABLED is the sole ownership gate. It now defaults ON, so
        this is belt-and-braces: it keeps these cases independent of the default
        should a future change flip it.
        """
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "true")

    @pytest.fixture(autouse=True)
    def _mock_periodic_tasks(self):
        # reconcile now bumps PeriodicTasks.last_update after the bulk .update();
        # mock it so these DB-free tests don't reach the real celery-beat singleton.
        with patch("scheduler.ownership.PeriodicTasks") as pts:
            yield pts

    def _patches(self, *, owner: bool, rows_matched: int = 1):
        sched = patch("scheduler.ownership.PgPeriodicSchedule")
        pt = patch("scheduler.ownership.PeriodicTask")
        resolve = patch("scheduler.ownership.resolve_schedule_owner", return_value=owner)
        # transaction.atomic() as a no-op context manager.
        txn = patch(
            "scheduler.ownership.transaction.atomic",
            return_value=contextlib.nullcontext(),
        )
        return sched, pt, resolve, txn

    def test_pg_owned_disables_beat_periodictask(self):
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt as PT, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            result = ownership.reconcile_ownership_for(_PID, _ORG, active=True)

        assert result is True
        # mirror pg_owned set True
        assert (
            Sched.objects.filter.return_value.update.call_args.kwargs["pg_owned"] is True
        )
        # Beat PeriodicTask disabled (active AND NOT pg_owned == False)
        PT.objects.filter.assert_called_once_with(name=_PID)
        assert PT.objects.filter.return_value.update.call_args.kwargs["enabled"] is False

    def test_not_pg_owned_enables_beat_and_clears_next_run(self):
        sched, pt, resolve, txn = self._patches(owner=False)
        with sched as Sched, pt as PT, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)

        update_kwargs = Sched.objects.filter.return_value.update.call_args.kwargs
        assert update_kwargs["pg_owned"] is False
        # Rollback to Beat clears next_run_at so a re-hand-over re-baselines.
        assert update_kwargs["next_run_at"] is None
        assert PT.objects.filter.return_value.update.call_args.kwargs["enabled"] is True

    def test_an_ALREADY_pg_owned_schedule_does_not_clear_next_run(self):
        """Narrowed: this is the True→True case, not "adopt never clears".

        Hand-over now DOES baseline (see TestNextRunBaselineOnTransition) — a
        next_run_at surviving adoption fires the pipeline immediately. What must not
        happen is re-baselining a schedule that was already PG-owned: reconcile runs on
        every pipeline save, so a save at 12:07:59 would push a 12:08 next_run_at out to
        13:08 and skip that fire.

        `was_pg_owned` is set explicitly — a bare MagicMock is truthy, so this would
        otherwise pass for the wrong reason and keep passing if the scoping regressed.
        """
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            qs = Sched.objects.filter.return_value
            qs.values_list.return_value.first.return_value = True
            qs.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)

        assert "next_run_at" not in qs.update.call_args.kwargs

    def test_paused_pipeline_keeps_beat_disabled_even_if_not_pg_owned(self):
        sched, pt, resolve, txn = self._patches(owner=False)
        with sched as Sched, pt as PT, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=False)

        # active=False → Beat stays disabled regardless of ownership.
        assert PT.objects.filter.return_value.update.call_args.kwargs["enabled"] is False

    def test_missing_mirror_row_skips_and_reports_beat(self):
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt as PT, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 0  # no row
            # No mirror row → PG can't fire → effective owner is Beat → returns
            # False even though resolve said PG (so the ramp count isn't inflated).
            assert ownership.reconcile_ownership_for(_PID, _ORG, active=True) is False

        PT.objects.filter.assert_not_called()  # nothing to own yet

    def test_failure_returns_none_and_is_swallowed(self):
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            Sched.objects.filter.return_value.update.side_effect = RuntimeError("db")
            # Must not raise, and signals failure (None) so the ramp can tally it.
            assert ownership.reconcile_ownership_for(_PID, _ORG, active=True) is None

    def test_beat_reload_signalled_after_handover(self, _mock_periodic_tasks):
        """The Beat PeriodicTask flip uses a bulk .update() (chosen to avoid
        clobbering a concurrent reconcile), which bypasses django-celery-beat's
        post_save signal. Without an explicit PeriodicTasks.update_changed() bump,
        DatabaseScheduler never reloads and Beat keeps firing the handed-over
        schedule from its stale in-memory copy (breaking no-double-fire).
        """
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)
        _mock_periodic_tasks.update_changed.assert_called_once_with()

    def test_beat_reload_not_signalled_when_no_mirror_row(self, _mock_periodic_tasks):
        """No mirror row → the method returns before touching the PeriodicTask, so
        no reload should be signalled either.
        """
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 0
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)
        _mock_periodic_tasks.update_changed.assert_not_called()


class TestPgSchedulerGate:
    """The gate deciding whether the PG scheduler or Beat owns a schedule.

    It defaults ON (UN-4046) — PG is the only transport and the PG scheduler ships
    with the fleet. It remains a gate because handing a schedule over while no PG
    scheduler is running leaves it with NO firer: Beat's PeriodicTask disabled,
    nothing polling the PG side.
    """

    def test_defaults_on(self, monkeypatch):
        monkeypatch.delenv("PG_SCHEDULER_ENABLED", raising=False)
        assert ownership.pg_scheduler_enabled() is True

    @pytest.mark.parametrize("value", ["false", "False", "0", "", "yes", "TRUE "])
    def test_only_an_exact_true_stays_on(self, monkeypatch, value):
        """Opting OUT is the deliberate act now — anything but an exact ``true``
        (case/whitespace-insensitive) turns the gate off.
        """
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", value)
        assert ownership.pg_scheduler_enabled() is (value.strip().lower() == "true")

    def test_owner_stays_beat_when_the_gate_is_off(self, monkeypatch):
        """A deployment that deliberately runs without worker-pg-scheduler."""
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        assert ownership.resolve_schedule_owner() is False

    def test_reconcile_writes_NEITHER_beat_table(self, monkeypatch):
        """The regression this gate exists to prevent.

        Returning early matters over merely resolving to Beat: that path would still
        issue PeriodicTask.update(enabled=active) and bump PeriodicTasks.update_changed()
        on every schedule save — writing back a value Beat already had and forcing a
        reload, on a table we promised not to touch.
        """
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        with (
            patch("scheduler.ownership.PeriodicTask") as PT,
            patch("scheduler.ownership.PeriodicTasks") as PTs,
            patch("scheduler.ownership.PgPeriodicSchedule") as Sched,
        ):
            # A CLEAN row: not pg_owned, so there is nothing to repair and the
            # write-free path must be taken. Must be set explicitly — a bare
            # MagicMock's .exists() is truthy, which would look like a stale row.
            Sched.objects.filter.return_value.exists.return_value = False
            assert ownership.reconcile_ownership_for(_PID, _ORG, active=True) is False

        PT.objects.filter.assert_not_called()
        PTs.update_changed.assert_not_called()
        # pg_owned is not WRITTEN either — otherwise switching the PG scheduler on
        # later would fire every already-owned schedule while Beat still fires it too.
        # (.filter() is now called once, for the read-only staleness check.)
        Sched.objects.filter.return_value.update.assert_not_called()


class TestStalePgOwnershipIsReleased:
    """A row left ``pg_owned`` by a build predating the gate must be repairable.

    Reproduced on integration 2026-08-12: `snapshot.993`'s backend came from OSS
    `main`, where ``resolve_schedule_owner`` keys on the ``pg_queue_enabled`` Flipt
    flag ALONE. Turning the flag on handed one pipeline to PG. Rolling forward onto
    the gate then STRANDED it: the gate-off path wrote nothing, so nothing —
    including ``reconcile_pg_schedules``, which routes back through here — could
    clear it. Beat and the PG scheduler both fired that pipeline 2.4s apart; only
    one execution resulted because the Celery consumers happened to be at zero.

    Reachable in production without a mis-built image: deploy this branch, roll back
    to a pre-gate build while the flag is on, roll forward.
    """

    def _mocks(self, stale: bool):
        sched = patch("scheduler.ownership.PgPeriodicSchedule").start()
        sched.objects.filter.return_value.exists.return_value = stale
        sched.objects.filter.return_value.update.return_value = 1
        # These tests are DB-free, but the repair path (unlike the write-free one)
        # enters the real transaction.atomic() — same no-op stand-in as above.
        patch(
            "scheduler.ownership.transaction.atomic",
            return_value=contextlib.nullcontext(),
        ).start()
        return sched

    def teardown_method(self):
        patch.stopall()

    def test_a_stale_row_is_handed_back_to_beat(self, monkeypatch):
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        sched = self._mocks(stale=True)
        with (
            patch("scheduler.ownership.PeriodicTask") as PT,
            patch("scheduler.ownership.PeriodicTasks") as PTs,
        ):
            assert ownership.reconcile_ownership_for(_PID, _ORG, active=True) is False

        # pg_owned cleared, and next_run_at reset so a later re-hand-over baselines
        # instead of firing immediately on a stale timestamp.
        updates = sched.objects.filter.return_value.update.call_args.kwargs
        assert updates["pg_owned"] is False
        assert updates["next_run_at"] is None
        # Beat re-enabled in the same breath — releasing pg_owned without this would
        # leave the schedule with NO firer at all.
        #
        # UN-3796 (2026-08-24): the write now also baselines Beat's clock, so this
        # asserts per-key rather than on the whole kwargs dict. Not a loosening — the
        # repair path is a RELEASE, and it is the one most likely to hand back a row
        # whose last_run_at is deeply stale, which is exactly what makes Beat replay
        # every missed interval at once. TestBeatClockBaselineOnRelease pins the rule.
        beat = PT.objects.filter.return_value.update.call_args.kwargs
        assert beat["enabled"] is True
        assert "last_run_at" in beat
        # ...and Beat told to reload, else it keeps its stale in-memory copy.
        PTs.update_changed.assert_called_once()

    def test_a_paused_pipeline_is_not_resurrected_by_the_repair(self, monkeypatch):
        """Repair restores the FIRER, never the on/off state the user chose."""
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        self._mocks(stale=True)
        with (
            patch("scheduler.ownership.PeriodicTask") as PT,
            patch("scheduler.ownership.PeriodicTasks"),
        ):
            ownership.reconcile_ownership_for(_PID, _ORG, active=False)
        beat = PT.objects.filter.return_value.update.call_args.kwargs
        assert beat["enabled"] is False
        # Baselined even though it stays paused: if it is resumed later, Beat must not
        # then replay the backlog accrued while PG owned it.
        assert "last_run_at" in beat

    def test_flipt_is_never_consulted_while_the_gate_is_off(self, monkeypatch):
        """The repair resolves to Beat unconditionally.

        Asking Flipt could return True and re-hand the schedule to a PG scheduler
        that is not running — turning a double-fire into no firer at all.
        """
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        self._mocks(stale=True)
        with (
            patch("scheduler.ownership.PeriodicTask"),
            patch("scheduler.ownership.PeriodicTasks"),
        ):
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)

    def test_a_db_error_on_the_check_falls_back_to_writing_nothing(self, monkeypatch):
        """A repair that cannot confirm it is needed must not run."""
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "false")
        sched = patch("scheduler.ownership.PgPeriodicSchedule").start()
        sched.objects.filter.side_effect = Exception("db down")
        with (
            patch("scheduler.ownership.PeriodicTask") as PT,
            patch("scheduler.ownership.PeriodicTasks") as PTs,
        ):
            assert ownership.reconcile_ownership_for(_PID, _ORG, active=True) is False
        PT.objects.filter.assert_not_called()
        PTs.update_changed.assert_not_called()


class TestReconcileAtomicityRealDB:
    """The load-bearing invariant: the pg_owned write and the PeriodicTask write
    are ONE transaction — if the PeriodicTask update fails, pg_owned rolls back
    (so a schedule can't end up pg_owned with Beat still enabled). Needs a real
    DB (the mocked atomic() can't prove rollback); skips if unreachable.
    """

    def test_periodictask_update_failure_rolls_back_pg_owned(self):
        import uuid

        from django_celery_beat.models import CrontabSchedule
        from django_celery_beat.models import PeriodicTask as RealPeriodicTask
        from pg_queue.models import PgPeriodicSchedule

        try:
            cron, _ = CrontabSchedule.objects.get_or_create(
                minute="0",
                hour="9",
                day_of_week="*",
                day_of_month="*",
                month_of_year="*",
            )
        except Exception as exc:  # pragma: no cover - infra-dependent
            pytest.skip(f"DB unavailable: {exc}")

        pid = str(uuid.uuid4())
        RealPeriodicTask.objects.create(
            name=pid,
            task="scheduler.tasks.execute_pipeline_task",
            crontab=cron,
            enabled=True,
            args="[]",
        )
        PgPeriodicSchedule.objects.create(
            pipeline_id=pid,
            organization_id="org_atomic",
            cron_string="0 9 * * *",
            enabled=True,
            pg_owned=False,
        )
        try:
            # Force the second write (the Beat PeriodicTask update) to fail; the
            # pg_owned write (real, before it in the same atomic) must roll back.
            failing_pt = MagicMock()
            failing_pt.objects.filter.return_value.update.side_effect = RuntimeError(
                "beat update fail"
            )
            with (
                patch("scheduler.ownership.resolve_schedule_owner", return_value=True),
                patch("scheduler.ownership.PeriodicTask", failing_pt),
            ):
                result = ownership.reconcile_ownership_for(pid, "org_atomic", active=True)
            assert result is None  # failure signalled
            # The pg_owned=True write was rolled back with the failed PT update.
            assert PgPeriodicSchedule.objects.get(pipeline_id=pid).pg_owned is False
        finally:
            RealPeriodicTask.objects.filter(name=pid).delete()
            PgPeriodicSchedule.objects.filter(pipeline_id=pid).delete()


class TestNextRunBaselineOnTransition:
    """An ownership or on/off change must never cause an immediate unscheduled run.

    The PG tick selects `WHERE pg_owned AND enabled AND (next_run_at IS NULL OR
    next_run_at <= now())`. A next_run_at left over from an earlier PG-ownership period
    is already in the past, so the row fires on the very next pass. NULL is the guard —
    "record a baseline next tick, don't fire this cycle" (pg_queue/models.py:366).

    Observed on integration 2026-08-14: gallh_load_test carried
    next_run_at=2026-08-12 06:08 and fired ~2s after being re-enabled — two days late,
    on top of the operator's own manual run.

    CORRECTION (2026-08-24): this docstring used to add "Beat never did this:
    DatabaseScheduler keeps no persisted next_run_at and recomputes due-ness from the
    crontab each tick." That is wrong. It recomputes from ``PeriodicTask.last_run_at``,
    which is precisely why it DOES catch up — releasing the fleet fired four pipelines
    and three periodics inside 30 ms. Beat has the same failure mode from the other
    direction; see TestBeatClockBaselineOnRelease below.
    """

    def _reconcile(self, monkeypatch, *, was_pg_owned, now_pg_owned):
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "true")
        with (
            patch("scheduler.ownership.PgPeriodicSchedule") as Sched,
            patch("scheduler.ownership.PeriodicTask"),
            patch("scheduler.ownership.PeriodicTasks"),
            patch(
                "scheduler.ownership.transaction.atomic",
                return_value=contextlib.nullcontext(),
            ),
            patch(
                "scheduler.ownership.resolve_schedule_owner",
                return_value=now_pg_owned,
            ),
        ):
            qs = Sched.objects.filter.return_value
            qs.values_list.return_value.first.return_value = was_pg_owned
            qs.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)
            return qs.update.call_args.kwargs

    def test_handing_over_to_pg_baselines(self, monkeypatch):
        # The bug: a stale next_run_at surviving adoption fires the pipeline at once.
        updates = self._reconcile(monkeypatch, was_pg_owned=False, now_pg_owned=True)
        assert updates["pg_owned"] is True
        assert updates["next_run_at"] is None

    def test_releasing_to_beat_still_baselines(self, monkeypatch):
        updates = self._reconcile(monkeypatch, was_pg_owned=True, now_pg_owned=False)
        assert updates["next_run_at"] is None

    def test_an_unchanged_owner_is_NOT_re_baselined(self, monkeypatch):
        """The reason this is scoped to the transition.

        reconcile runs on every pipeline save. Clearing unconditionally would let a
        save at 12:07:59 re-baseline a 12:08 next_run_at to 13:08 — silently skipping
        that fire. Idempotent re-runs (every deploy) must leave the schedule alone.
        """
        updates = self._reconcile(monkeypatch, was_pg_owned=True, now_pg_owned=True)
        assert "next_run_at" not in updates


class TestBeatClockBaselineOnRelease:
    """Handing a schedule BACK to Beat must reset Beat's clock, or Beat replays.

    The symmetric half of the class above, and the one that was missing.
    DatabaseScheduler stores no next_run_at; it derives due-ness from
    ``PeriodicTask.last_run_at`` against the crontab. A pipeline that spent days
    PG-owned still carries the last_run_at from before the hand-over, so the instant
    ``enabled`` flips back it is overdue by every interval it missed — and Beat fires
    them all at once.

    Observed on integration 2026-08-24: `converge_pg_scheduler` released 23 schedules
    and Beat dispatched four pipelines plus three dashboard_metrics.* periodics within
    30 ms of logging "Released to Beat".
    """

    def _reconcile(self, monkeypatch, *, was_pg_owned, now_pg_owned, active=True):
        monkeypatch.setenv("PG_SCHEDULER_ENABLED", "true")
        with (
            patch("scheduler.ownership.PgPeriodicSchedule") as Sched,
            patch("scheduler.ownership.PeriodicTask") as Beat,
            patch("scheduler.ownership.PeriodicTasks"),
            patch(
                "scheduler.ownership.transaction.atomic",
                return_value=contextlib.nullcontext(),
            ),
            patch(
                "scheduler.ownership.resolve_schedule_owner",
                return_value=now_pg_owned,
            ),
        ):
            qs = Sched.objects.filter.return_value
            qs.values_list.return_value.first.return_value = was_pg_owned
            qs.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=active)
            return Beat.objects.filter.return_value.update.call_args.kwargs

    def test_releasing_to_beat_stamps_last_run_at(self, monkeypatch):
        beat = self._reconcile(monkeypatch, was_pg_owned=True, now_pg_owned=False)
        assert beat["enabled"] is True
        assert "last_run_at" in beat, (
            "release must baseline Beat's clock, else every interval missed while "
            "PG owned the schedule is overdue and Beat replays them at once"
        )
        assert beat["last_run_at"] is not None

    def test_handing_over_to_pg_does_NOT_touch_beats_clock(self, monkeypatch):
        """Adoption switches Beat OFF, so its clock is irrelevant — and overwriting it
        would destroy the value the eventual release needs to restore from.
        """
        beat = self._reconcile(monkeypatch, was_pg_owned=False, now_pg_owned=True)
        assert beat["enabled"] is False
        assert "last_run_at" not in beat

    def test_an_unchanged_owner_is_NOT_re_stamped(self, monkeypatch):
        """Same transition-scoping reason as next_run_at: reconcile runs on every
        pipeline save, and stamping unconditionally would push Beat's clock forward
        on an ordinary edit and silently skip a due fire.
        """
        beat = self._reconcile(monkeypatch, was_pg_owned=False, now_pg_owned=False)
        assert "last_run_at" not in beat

    def test_a_paused_pipeline_is_released_disabled_but_still_baselined(
        self, monkeypatch
    ):
        """A paused schedule comes back paused — but if it is later resumed, Beat must
        not then replay the backlog it accrued while PG owned it.
        """
        beat = self._reconcile(
            monkeypatch, was_pg_owned=True, now_pg_owned=False, active=False
        )
        assert beat["enabled"] is False
        assert "last_run_at" in beat
