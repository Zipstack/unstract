"""Unit tests for the inert pg_periodic_schedule mirror (Phase 9, ②a).

DB-free: ``PgPeriodicSchedule`` (and the django_celery_beat models / serializer)
are mocked, so these pin the dual-write contract — that every schedule mutation
mirrors the right fields, that the mirror stores the *real* pipeline name (not
the synthetic ``"Pipeline job-<id>"`` label carried in the PeriodicTask args),
and that a mirror failure can never break the existing Celery Beat scheduling
path — without a test database.
"""

from contextlib import nullcontext
from datetime import datetime
from datetime import timezone as dt_timezone
from unittest.mock import MagicMock, patch

from scheduler import tasks
from scheduler.helper import SchedulerHelper

_PIPELINE_ID = "11111111-1111-1111-1111-111111111111"
_WORKFLOW_ID = "22222222-2222-2222-2222-222222222222"
_ORG = "org_abc"
_REAL_NAME = "Nightly Invoices ETL"


class _DoesNotExist(Exception):
    """Stand-in for PeriodicTask.DoesNotExist when the model is mocked."""


def _stub_existing_row(sched, row=None):
    """Stub the ``.filter().values().first()`` read of the existing mirror row
    (``None`` = no row yet). The one place the read shape lives, so a change to how
    the code reads the row (e.g. ``.only()`` instead of ``.values()``) is a
    one-line edit here."""
    sched.objects.filter.return_value.values.return_value.first.return_value = row


class TestUpsertMirror:
    def test_upserts_with_given_fields(self):
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            _stub_existing_row(sched)
            tasks.mirror_periodic_schedule_upsert(
                pipeline_id=_PIPELINE_ID,
                organization_id=_ORG,
                workflow_id=_WORKFLOW_ID,
                pipeline_name=_REAL_NAME,
                cron_string="0 9 * * *",
                enabled=True,
            )
        call = sched.objects.update_or_create.call_args
        assert call.kwargs["pipeline_id"] == _PIPELINE_ID
        defaults = call.kwargs["defaults"]
        assert defaults["organization_id"] == _ORG
        assert defaults["workflow_id"] == _WORKFLOW_ID
        assert defaults["pipeline_name"] == _REAL_NAME
        assert defaults["cron_string"] == "0 9 * * *"
        assert defaults["enabled"] is True

    def test_disabled_pipeline_mirrors_enabled_false(self):
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            _stub_existing_row(sched)
            tasks.mirror_periodic_schedule_upsert(
                pipeline_id=_PIPELINE_ID,
                organization_id=_ORG,
                workflow_id=_WORKFLOW_ID,
                pipeline_name=_REAL_NAME,
                cron_string="0 9 * * *",
                enabled=False,
            )
        assert sched.objects.update_or_create.call_args.kwargs["defaults"]["enabled"] is False

    def test_failure_is_swallowed(self):
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            _stub_existing_row(sched)
            sched.objects.update_or_create.side_effect = RuntimeError("db down")
            # Must not raise.
            tasks.mirror_periodic_schedule_upsert(
                pipeline_id=_PIPELINE_ID,
                organization_id=_ORG,
                workflow_id=_WORKFLOW_ID,
                pipeline_name=_REAL_NAME,
                cron_string="0 9 * * *",
                enabled=True,
            )


class _UpsertNextRunHelpers:
    """Shared setup for the two ``next_run_at`` suites below. Helpers only — no
    tests live here, so neither suite re-runs the other's cases."""

    _OLD = datetime(2026, 1, 1, 9, 0, tzinfo=dt_timezone.utc)

    @staticmethod
    def _mock_existing(sched, *, cron_string, next_run_at, enabled=True):
        _stub_existing_row(
            sched,
            None
            if cron_string is None
            else {
                "cron_string": cron_string,
                "next_run_at": next_run_at,
                "enabled": enabled,
            },
        )

    @staticmethod
    def _upsert(cron, enabled=True):
        tasks.mirror_periodic_schedule_upsert(
            pipeline_id=_PIPELINE_ID,
            organization_id=_ORG,
            workflow_id=_WORKFLOW_ID,
            pipeline_name=_REAL_NAME,
            cron_string=cron,
            enabled=enabled,
        )

    @staticmethod
    def _defaults(sched):
        return sched.objects.update_or_create.call_args.kwargs["defaults"]


class TestUpsertNextRunRecompute(_UpsertNextRunHelpers):
    """UN-3690 — a cron EDIT must retarget ``next_run_at`` (Beat parity), so the
    new time takes effect this cycle instead of the pipeline firing once more at
    the stale old-cron time. Only for an already-baselined row: a fresh row and a
    Beat→PG hand-over keep ``next_run_at`` NULL for the scheduler's no-burst
    baseline.
    """

    def test_cron_change_on_baselined_row_retargets_next_run_at(self):
        now = datetime(2026, 1, 1, 8, 0, tzinfo=dt_timezone.utc)
        with (
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
            patch("scheduler.tasks.timezone.now", return_value=now),
        ):
            self._mock_existing(sched, cron_string="0 9 * * *", next_run_at=self._OLD)
            self._upsert("0 10 * * *")  # edited to a new time
        defaults = self._defaults(sched)
        # Assert the concrete constant (not a croniter self-echo) — pins both the
        # value AND tz-awareness: the next 10:00 UTC after 08:00, off the NEW cron.
        assert defaults["next_run_at"] == datetime(2026, 1, 1, 10, 0, tzinfo=dt_timezone.utc)
        assert defaults["cron_string"] == "0 10 * * *"  # retarget ships with new cron

    def test_unchanged_cron_leaves_next_run_at_untouched(self):
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(sched, cron_string="0 9 * * *", next_run_at=self._OLD)
            self._upsert("0 9 * * *")  # same cron (e.g. a rename)
        assert "next_run_at" not in self._defaults(sched)

    def test_null_next_run_at_left_for_baseline(self):
        # Not-yet-baselined row (fresh mirror / Beat→PG hand-over) → keep NULL so
        # the scheduler baseline records the first next-time (no double-retarget).
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(sched, cron_string="0 9 * * *", next_run_at=None)
            self._upsert("0 10 * * *")
        assert "next_run_at" not in self._defaults(sched)

    def test_new_row_does_not_set_next_run_at(self):
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(sched, cron_string=None, next_run_at=None)  # → None
            self._upsert("0 10 * * *")
        assert "next_run_at" not in self._defaults(sched)

    def test_invalid_cron_leaves_stale_next_run_at_but_still_upserts(self):
        # An unparseable cron must not block the mirror write; next_run_at is left
        # as-is (the scheduler quiesces a bad cron on its own tick).
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(sched, cron_string="0 9 * * *", next_run_at=self._OLD)
            self._upsert("not a cron")
        assert sched.objects.update_or_create.called
        assert "next_run_at" not in self._defaults(sched)

    def test_read_failure_degrades_to_plain_upsert(self):
        # The optional next_run_at recompute must NEVER take down the mandatory
        # cron_string/enabled mirror write: a failure in the existing-row read
        # degrades to exactly the pre-PR behaviour (plain upsert, no next_run_at)
        # and never raises (the "never break Beat" guarantee) — UN-3690.
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            sched.objects.filter.side_effect = RuntimeError("db down")
            self._upsert("0 10 * * *")  # must not raise
        assert sched.objects.update_or_create.called  # base mirror write still ran
        assert "next_run_at" not in self._defaults(sched)


class TestUpsertResumeBaselinesStaleNextRun(_UpsertNextRunHelpers):
    """A UI resume must not fire a catch-up run.

    ``enable_task`` baselines ``next_run_at`` on resume, but the UI does not take
    that path — it re-saves the pipeline, reaching
    ``SchedulerHelper._schedule_task_job`` → ``mirror_periodic_schedule_upsert``
    (here) and ``reconcile_ownership_for``. The latter baselines only on a
    Beat→PG hand-over, so a row that is ALREADY ``pg_owned`` keeps whatever
    ``next_run_at`` it had when it was paused — days in the past — and the PG
    tick's ``next_run_at <= now()`` fires it on the very next pass.

    Observed three times on integration (2026-08-12, -14, -20): each enable of
    ``gallh_load_test`` produced a spurious run 2-3s later, then settled onto the
    cron correctly.
    """

    def test_resume_clears_a_stale_next_run_at(self):
        """The bug, directly: paused row + past next_run_at, re-enabled."""
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(
                sched, cron_string="8 * * * *", next_run_at=self._OLD, enabled=False
            )
            self._upsert("8 * * * *", enabled=True)
        defaults = self._defaults(sched)
        # Present AND None: writing NULL is the baseline instruction. Merely
        # omitting the key would leave the stale value in place — the bug.
        assert "next_run_at" in defaults
        assert defaults["next_run_at"] is None

    def test_resume_that_also_edits_the_cron_still_baselines(self):
        """Resume is checked before the cron comparison, so a combined
        resume+edit baselines rather than retargeting. Both are non-firing, but
        this pins the ordering — reversing it would let the equal-cron early-out
        swallow the common plain-resume case."""
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(
                sched, cron_string="0 9 * * *", next_run_at=self._OLD, enabled=False
            )
            self._upsert("0 10 * * *", enabled=True)
        assert self._defaults(sched)["next_run_at"] is None

    def test_a_save_on_an_already_enabled_row_is_untouched(self):
        """The mid-cycle guard. This helper runs on EVERY pipeline save, so a
        rename at 12:07:59 against a 12:08 next_run_at must not re-baseline and
        skip that fire. Only the False→True transition clears."""
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(
                sched, cron_string="8 * * * *", next_run_at=self._OLD, enabled=True
            )
            self._upsert("8 * * * *", enabled=True)
        assert "next_run_at" not in self._defaults(sched)

    def test_pause_does_not_clear_next_run_at(self):
        """Nothing fires while disabled, so there is nothing to guard against —
        and clearing here would discard the value resume needs to detect."""
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(
                sched, cron_string="8 * * * *", next_run_at=self._OLD, enabled=True
            )
            self._upsert("8 * * * *", enabled=False)
        assert "next_run_at" not in self._defaults(sched)

    def test_resume_of_a_never_baselined_row_writes_nothing(self):
        """next_run_at already NULL is already the baseline — no write needed,
        and the read short-circuits before the enabled check."""
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
            self._mock_existing(
                sched, cron_string="8 * * * *", next_run_at=None, enabled=False
            )
            self._upsert("8 * * * *", enabled=True)
        assert "next_run_at" not in self._defaults(sched)

    def test_the_sentinel_is_not_none(self):
        """The whole fix rests on 'leave alone' being distinguishable from 'write
        NULL'. If the sentinel were None-y, the resume baseline would silently
        degrade back to the old skip-the-write behaviour and every test above
        would still pass on the omission path."""
        assert tasks._LEAVE_NEXT_RUN_AT is not None


class TestHelperWiringSourcesRealName:
    """The High contract: the mirror must store the user-facing pipeline name,
    NOT the synthetic ``"Pipeline job-<id>"`` label that the PeriodicTask args
    carry at index 6."""

    def test_schedule_task_job_passes_real_pipeline_name(self):
        pipeline = MagicMock()
        pipeline.pk = _PIPELINE_ID
        pipeline.pipeline_name = _REAL_NAME
        pipeline.active = True
        pipeline.workflow.id = _WORKFLOW_ID

        serializer = MagicMock()
        serializer.get_workflow_id.return_value = _WORKFLOW_ID
        serializer.get_execution_action.return_value = ""

        with (
            patch("scheduler.helper.ExecuteWorkflowSerializer", return_value=serializer),
            patch(
                "scheduler.helper.UserContext.get_organization_identifier",
                return_value=_ORG,
            ),
            patch("scheduler.helper.create_or_update_periodic_task"),
            patch("scheduler.helper.mirror_periodic_schedule_upsert") as mirror,
            patch("scheduler.helper.reconcile_ownership_for") as reconcile,
        ):
            SchedulerHelper._schedule_task_job(
                pipeline,
                {
                    "cron_string": "0 9 * * *",
                    "id": _PIPELINE_ID,
                    "name": f"Pipeline job-{_PIPELINE_ID}",  # the synthetic label
                },
            )

        mirror.assert_called_once()
        kwargs = mirror.call_args.kwargs
        assert kwargs["pipeline_name"] == _REAL_NAME  # real name, not the label
        assert kwargs["pipeline_id"] == _PIPELINE_ID
        assert kwargs["organization_id"] == _ORG
        assert kwargs["enabled"] is True
        # ②c: ownership is reconciled after the mirror upsert (org-identifier +
        # active passed through; active is keyword-only).
        reconcile.assert_called_once_with(_PIPELINE_ID, _ORG, active=True)


class TestEnableDisableMirror:
    def test_disable_mirrors_enabled_false(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            sched.objects.filter.return_value.update.return_value = 1
            tasks.disable_task(_PIPELINE_ID)

        sched.objects.filter.assert_called_with(pipeline_id=_PIPELINE_ID)
        assert sched.objects.filter.return_value.update.call_args.kwargs["enabled"] is False

    @staticmethod
    def _set_pg_owned(sched, value):
        # enable_task reads pg_owned via select_for_update().filter().values_list().first()
        (
            sched.objects.select_for_update.return_value.filter.return_value.values_list.return_value.first.return_value
        ) = value

    def test_resume_enables_beat_when_not_pg_owned(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PeriodicTasks") as pts,
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
            patch("scheduler.tasks.transaction.atomic", return_value=nullcontext()),
        ):
            pt.objects.get.return_value = MagicMock()
            self._set_pg_owned(sched, False)
            tasks.enable_task(_PIPELINE_ID)

        # Beat enabled via a column-only .update() (no full task.save() to clobber)
        assert pt.objects.filter.return_value.update.call_args.kwargs["enabled"] is True
        # ...but a bulk .update() skips celery-beat's post_save signal, so the
        # resume MUST bump PeriodicTasks.last_update or DatabaseScheduler never
        # reloads and the resumed pipeline silently never fires.
        pts.update_changed.assert_called_once_with()

    def test_resume_keeps_beat_disabled_when_pg_owned(self):
        """The High bug: resuming a PG-owned schedule must NOT re-enable Beat
        (both firing = double-fire)."""
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PeriodicTasks"),
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
            patch("scheduler.tasks.transaction.atomic", return_value=nullcontext()),
        ):
            pt.objects.get.return_value = MagicMock()
            self._set_pg_owned(sched, True)
            tasks.enable_task(_PIPELINE_ID)

        # PG owns it → Beat stays off.
        assert pt.objects.filter.return_value.update.call_args.kwargs["enabled"] is False

    def test_disable_mirror_failure_does_not_break_beat_path(self):
        """A mirror failure must be swallowed AND the pipeline-status update must
        still run (the central 'never break Beat' guarantee)."""
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PipelineProcessor") as pp,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            sched.objects.filter.return_value.update.side_effect = RuntimeError("db down")
            tasks.disable_task(_PIPELINE_ID)  # must not raise

        pp.update_pipeline.assert_called_once()

    def test_unmirrored_pipeline_logs_zero_match(self, caplog):
        import logging

        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            sched.objects.filter.return_value.update.return_value = 0  # no mirror row
            with caplog.at_level(logging.INFO, logger="scheduler.tasks"):
                tasks.disable_task(_PIPELINE_ID)

        assert any("matched 0 rows" in r.message for r in caplog.records)


class TestDeleteMirror:
    def test_delete_removes_mirror_row(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            tasks.delete_periodic_task(_PIPELINE_ID)

        sched.objects.filter.assert_called_with(pipeline_id=_PIPELINE_ID)
        sched.objects.filter.return_value.delete.assert_called_once()

    def test_delete_cleans_mirror_even_when_periodictask_missing(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.DoesNotExist = _DoesNotExist
            pt.objects.get.side_effect = _DoesNotExist()
            tasks.delete_periodic_task(_PIPELINE_ID)  # must not raise

        sched.objects.filter.return_value.delete.assert_called_once()

    def test_delete_mirror_failure_is_swallowed(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            sched.objects.filter.return_value.delete.side_effect = RuntimeError("db down")
            tasks.delete_periodic_task(_PIPELINE_ID)  # must not raise


class TestResumeBaselinesInsteadOfCatchingUp:
    """Re-enabling a paused schedule must resume at the next cron match, not fire now.

    While a schedule is paused its `next_run_at` keeps drifting into the past, so the
    PG tick's `next_run_at <= now()` matches on the very next pass and the pipeline runs
    IMMEDIATELY on resume — the longer the pause, the more certain. NULL is the guard:
    "record a baseline next tick, don't fire this cycle" (pg_queue/models.py:366).

    Observed on integration 2026-08-14: gallh_load_test fired ~2s after being
    re-enabled, against a next_run_at two days old, on top of the operator's manual run.

    CORRECTION (2026-08-24): this docstring used to claim "Beat parity, not a new rule —
    DatabaseScheduler ... recomputes due-ness from the crontab each tick, so resume
    never produced a catch-up run there." Wrong on the mechanism: it recomputes from
    PeriodicTask.last_run_at, so Beat catches up as well. Both schedulers need their
    clock baselined on a hand-over; the Beat half is pinned by
    scheduler/tests/test_pg_schedule_ownership.py::TestBeatClockBaselineOnRelease.
    """

    def _run(self, fn):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PeriodicTasks"),
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
            patch("scheduler.tasks.transaction.atomic", return_value=nullcontext()),
        ):
            pt.objects.get.return_value = MagicMock()
            (
                sched.objects.select_for_update.return_value.filter.return_value
                .values_list.return_value.first.return_value
            ) = False
            sched.objects.filter.return_value.update.return_value = 1
            fn(_PIPELINE_ID)
            return sched.objects.filter.return_value.update.call_args.kwargs

    def test_resume_clears_next_run_at(self):
        kwargs = self._run(tasks.enable_task)
        assert kwargs["enabled"] is True
        assert kwargs["next_run_at"] is None

    def test_pause_leaves_next_run_at_alone(self):
        """Nothing fires while disabled, so there is nothing to guard against — and
        clearing here would discard the value resume needs to baseline against.
        """
        kwargs = self._run(tasks.disable_task)
        assert kwargs["enabled"] is False
        assert "next_run_at" not in kwargs
