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
    def test_flipt_unavailable_is_beat(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "false")
        with patch("scheduler.ownership.check_feature_flag_status") as flag:
            assert ownership.resolve_schedule_owner(_PID, _ORG) is False
            flag.assert_not_called()

    def test_flag_true_is_pg(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(
            "scheduler.ownership.check_feature_flag_status", return_value=True
        ) as flag:
            assert ownership.resolve_schedule_owner(_PID, _ORG) is True
            # entity_id = pipeline_id (stable %-bucket); org in context.
            assert flag.call_args.kwargs["entity_id"] == _PID
            assert flag.call_args.kwargs["context"]["pipeline_id"] == _PID
            assert flag.call_args.kwargs["context"]["organization_id"] == _ORG

    def test_flag_false_is_beat(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(
            "scheduler.ownership.check_feature_flag_status", return_value=False
        ):
            assert ownership.resolve_schedule_owner(_PID, _ORG) is False

    def test_flipt_error_fails_closed_to_beat(self, monkeypatch):
        monkeypatch.setenv("FLIPT_SERVICE_AVAILABLE", "true")
        with patch(
            "scheduler.ownership.check_feature_flag_status",
            side_effect=RuntimeError("flipt down"),
        ):
            assert ownership.resolve_schedule_owner(_PID, _ORG) is False


class TestReconcileOwnership:
    @pytest.fixture(autouse=True)
    def _mock_periodic_tasks(self):
        # reconcile now bumps PeriodicTasks.last_update after the bulk .update();
        # mock it so these DB-free tests don't reach the real celery-beat singleton.
        with patch("scheduler.ownership.PeriodicTasks") as pts:
            yield pts

    def _patches(self, *, owner: bool, rows_matched: int = 1):
        sched = patch("scheduler.ownership.PgPeriodicSchedule")
        pt = patch("scheduler.ownership.PeriodicTask")
        resolve = patch(
            "scheduler.ownership.resolve_schedule_owner", return_value=owner
        )
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
            Sched.objects.filter.return_value.update.call_args.kwargs["pg_owned"]
            is True
        )
        # Beat PeriodicTask disabled (active AND NOT pg_owned == False)
        PT.objects.filter.assert_called_once_with(name=_PID)
        assert (
            PT.objects.filter.return_value.update.call_args.kwargs["enabled"] is False
        )

    def test_not_pg_owned_enables_beat_and_clears_next_run(self):
        sched, pt, resolve, txn = self._patches(owner=False)
        with sched as Sched, pt as PT, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)

        update_kwargs = Sched.objects.filter.return_value.update.call_args.kwargs
        assert update_kwargs["pg_owned"] is False
        # Rollback to Beat clears next_run_at so a re-hand-over re-baselines.
        assert update_kwargs["next_run_at"] is None
        assert (
            PT.objects.filter.return_value.update.call_args.kwargs["enabled"] is True
        )

    def test_pg_owned_does_not_clear_next_run(self):
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)

        # An active PG-owned schedule must NOT have its next_run_at reset (that
        # would re-baseline and skip a fire).
        assert (
            "next_run_at"
            not in Sched.objects.filter.return_value.update.call_args.kwargs
        )

    def test_paused_pipeline_keeps_beat_disabled_even_if_not_pg_owned(self):
        sched, pt, resolve, txn = self._patches(owner=False)
        with sched as Sched, pt as PT, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=False)

        # active=False → Beat stays disabled regardless of ownership.
        assert (
            PT.objects.filter.return_value.update.call_args.kwargs["enabled"] is False
        )

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
        schedule from its stale in-memory copy (breaking no-double-fire)."""
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 1
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)
        _mock_periodic_tasks.update_changed.assert_called_once_with()

    def test_beat_reload_not_signalled_when_no_mirror_row(self, _mock_periodic_tasks):
        """No mirror row → the method returns before touching the PeriodicTask, so
        no reload should be signalled either."""
        sched, pt, resolve, txn = self._patches(owner=True)
        with sched as Sched, pt, resolve, txn:
            Sched.objects.filter.return_value.update.return_value = 0
            ownership.reconcile_ownership_for(_PID, _ORG, active=True)
        _mock_periodic_tasks.update_changed.assert_not_called()


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
                result = ownership.reconcile_ownership_for(
                    pid, "org_atomic", active=True
                )
            assert result is None  # failure signalled
            # The pg_owned=True write was rolled back with the failed PT update.
            assert PgPeriodicSchedule.objects.get(pipeline_id=pid).pg_owned is False
        finally:
            RealPeriodicTask.objects.filter(name=pid).delete()
            PgPeriodicSchedule.objects.filter(pipeline_id=pid).delete()
