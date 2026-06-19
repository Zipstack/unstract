"""Unit tests for the inert pg_periodic_schedule mirror (Phase 9, ②a).

DB-free: ``PgPeriodicSchedule`` (and the django_celery_beat models / serializer)
are mocked, so these pin the dual-write contract — that every schedule mutation
mirrors the right fields, that the mirror stores the *real* pipeline name (not
the synthetic ``"Pipeline job-<id>"`` label carried in the PeriodicTask args),
and that a mirror failure can never break the existing Celery Beat scheduling
path — without a test database.
"""

from unittest.mock import MagicMock, patch

from scheduler import tasks
from scheduler.helper import SchedulerHelper

_PIPELINE_ID = "11111111-1111-1111-1111-111111111111"
_WORKFLOW_ID = "22222222-2222-2222-2222-222222222222"
_ORG = "org_abc"
_REAL_NAME = "Nightly Invoices ETL"


class _DoesNotExist(Exception):
    """Stand-in for PeriodicTask.DoesNotExist when the model is mocked."""


class TestUpsertMirror:
    def test_upserts_with_given_fields(self):
        with patch("scheduler.tasks.PgPeriodicSchedule") as sched:
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
        # active passed through).
        reconcile.assert_called_once_with(_PIPELINE_ID, _ORG, True)


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

    def test_enable_mirrors_enabled_true(self):
        with (
            patch("scheduler.tasks.PeriodicTask") as pt,
            patch("scheduler.tasks.PipelineProcessor"),
            patch("scheduler.tasks.PgPeriodicSchedule") as sched,
        ):
            pt.objects.get.return_value = MagicMock()
            sched.objects.filter.return_value.update.return_value = 1
            tasks.enable_task(_PIPELINE_ID)

        assert sched.objects.filter.return_value.update.call_args.kwargs["enabled"] is True

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
