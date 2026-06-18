"""Unit tests for the inert pg_periodic_schedule mirror (Phase 9, ②a).

DB-free: ``PgPeriodicSchedule`` (and the django_celery_beat models) are mocked,
so these pin the dual-write contract — that every schedule mutation mirrors the
right fields into pg_periodic_schedule, and that a mirror failure can never
break the existing Celery Beat scheduling path — without a test database.
"""

from unittest.mock import MagicMock, patch

from scheduler import tasks

# Canonical task_args layout set by SchedulerHelper._schedule_task_job:
# [workflow_id, organization_id, execution_action, "", pipeline_id, False, name]
_PIPELINE_ID = "11111111-1111-1111-1111-111111111111"
_WORKFLOW_ID = "22222222-2222-2222-2222-222222222222"
_ORG = "org_abc"
_NAME = "Nightly ETL"
_ARGS = [_WORKFLOW_ID, _ORG, "", "", _PIPELINE_ID, False, _NAME]


class _DoesNotExist(Exception):
    """Stand-in for PeriodicTask.DoesNotExist when the model is mocked."""


class TestCreateOrUpdateMirror:
    def test_upserts_mirror_with_extracted_fields(self):
        with (
            patch("scheduler.tasks.CrontabSchedule") as cron,
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            cron.objects.get_or_create.return_value = (MagicMock(), True)
            pt.objects.update_or_create.return_value = (MagicMock(), True)

            tasks.create_or_update_periodic_task(
                cron_string="0 9 * * *",
                task_name=_PIPELINE_ID,
                task_path="scheduler.tasks.execute_pipeline_task",
                task_args=_ARGS,
                enabled=True,
            )

        sched.objects.update_or_create.assert_called_once()
        call = sched.objects.update_or_create.call_args
        assert call.kwargs["pipeline_id"] == _PIPELINE_ID
        defaults = call.kwargs["defaults"]
        assert defaults["organization_id"] == _ORG
        assert defaults["workflow_id"] == _WORKFLOW_ID
        assert defaults["pipeline_name"] == _NAME
        assert defaults["cron_string"] == "0 9 * * *"
        assert defaults["enabled"] is True

    def test_mirror_failure_does_not_break_beat_path(self):
        """A mirror write that raises must be swallowed — the PeriodicTask
        upsert still happens and no exception propagates to the caller."""
        with (
            patch("scheduler.tasks.CrontabSchedule") as cron,
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            cron.objects.get_or_create.return_value = (MagicMock(), True)
            pt.objects.update_or_create.return_value = (MagicMock(), True)
            sched.objects.update_or_create.side_effect = RuntimeError("db down")

            # Must NOT raise.
            tasks.create_or_update_periodic_task(
                cron_string="0 9 * * *",
                task_name=_PIPELINE_ID,
                task_path="scheduler.tasks.execute_pipeline_task",
                task_args=_ARGS,
                enabled=True,
            )

        # The Beat-side write still happened.
        pt.objects.update_or_create.assert_called_once()


class TestEnableDisableMirror:
    def test_disable_mirrors_enabled_false(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            tasks.disable_task(_PIPELINE_ID)

        sched.objects.filter.assert_called_once_with(pipeline_id=_PIPELINE_ID)
        sched.objects.filter.return_value.update.assert_called_once_with(enabled=False)

    def test_enable_mirrors_enabled_true(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            tasks.enable_task(_PIPELINE_ID)

        sched.objects.filter.return_value.update.assert_called_once_with(enabled=True)


class TestDeleteMirror:
    def test_delete_removes_mirror_row(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            tasks.delete_periodic_task(_PIPELINE_ID)

        sched.objects.filter.assert_called_once_with(pipeline_id=_PIPELINE_ID)
        sched.objects.filter.return_value.delete.assert_called_once()

    def test_delete_cleans_mirror_even_when_periodictask_missing(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.DoesNotExist = _DoesNotExist
            pt.objects.get.side_effect = _DoesNotExist()
            # Must not raise, and the mirror is still cleaned.
            tasks.delete_periodic_task(_PIPELINE_ID)

        sched.objects.filter.return_value.delete.assert_called_once()
