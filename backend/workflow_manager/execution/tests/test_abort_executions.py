"""``POST execution/abort/`` (UN-4318): owner-or-admin, per-id outcomes, audit."""

import uuid
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock, patch

from account_v2.models import Organization
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from platform_audit.actions import Action, TargetType
from platform_audit.models import PlatformAuditEvent
from tenant_account_v2.tests import _add_viewers, _make_user

from workflow_manager.execution.abort import ABORT_ERROR_MESSAGE, MAX_ABORT_IDS
from workflow_manager.execution.tests import test_update_status_locking as locking
from workflow_manager.execution.tests.stuck_abort_base import RECENT, StuckAbortTestBase
from workflow_manager.execution.views import ExecutionAbortView
from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.file_execution.serializers import FileCentricExecutionSerializer
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.execution import WorkflowExecutionServiceHelper
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

_abort = ExecutionAbortView.as_view()


class AbortExecutionTests(StuckAbortTestBase):
    def _abort(self, user: Any, *ids: Any, raw: dict[str, Any] | None = None) -> Any:
        body = raw if raw is not None else {"ids": [str(i) for i in ids]}
        return self.call(_abort, user, method="post", data=body)

    def _outcomes(self, response: Any) -> dict[str, tuple[str, str | None]]:
        self.assertEqual(response.status_code, 200, response.data)
        return {
            row["id"]: (row["outcome"], row["status"])
            for row in response.data["results"]
        }

    def _status(self, execution: WorkflowExecution) -> str:
        execution.refresh_from_db()
        status: str = execution.status
        return status

    def test_abort_stops_the_run_and_its_open_files_only(self) -> None:
        execution = self.execution(self.deployment(), idle=RECENT)
        done = self.file(execution, ExecutionStatus.COMPLETED, idle=RECENT)
        running = self.file(execution, ExecutionStatus.EXECUTING, idle=RECENT)
        queued = self.file(execution, ExecutionStatus.PENDING, idle=RECENT)
        failed = self.file(execution, ExecutionStatus.ERROR, idle=RECENT)
        WorkflowFileExecution.objects.filter(pk=failed.pk).update(execution_error="boom")

        response = self._abort(self.owner, execution.id)

        self.assertEqual(
            self._outcomes(response), {str(execution.id): ("aborted", "STOPPED")}
        )
        self.assertEqual(
            (response.data["aborted"], response.data["already_finished"]), (1, 0)
        )
        execution.refresh_from_db()
        self.assertEqual(execution.status, ExecutionStatus.STOPPED.value)
        self.assertEqual(execution.error_message, ABORT_ERROR_MESSAGE)
        for row, expected in (
            (done, ExecutionStatus.COMPLETED),
            (running, ExecutionStatus.STOPPED),
            (queued, ExecutionStatus.STOPPED),
            (failed, ExecutionStatus.ERROR),
        ):
            row.refresh_from_db()
            self.assertEqual(row.status, expected.value)
        self.assertIsNone(done.execution_error)
        self.assertEqual(failed.execution_error, "boom")
        self.assertEqual(running.execution_error, ABORT_ERROR_MESSAGE)
        self.assertEqual(queued.execution_error, ABORT_ERROR_MESSAGE)

    def test_stopped_file_row_shows_the_abort_and_a_fixed_time(self) -> None:
        execution = self.execution(idle=RECENT)
        row = self.file(execution, ExecutionStatus.EXECUTING, idle=RECENT)
        started = timezone.now() - timedelta(hours=1)
        WorkflowFileExecution.objects.filter(pk=row.pk).update(created_at=started)

        self._abort(self.owner, execution.id)

        row.refresh_from_db()
        self.assertAlmostEqual(row.execution_time, 3600, delta=60)
        self.assertEqual(
            FileCentricExecutionSerializer().get_status_msg(row), ABORT_ERROR_MESSAGE
        )

    def test_abort_writes_the_file_counts_counting_the_unfinished_as_failed(self) -> None:
        for known_total, total in ((5, 5), (0, 3)):
            with self.subTest(known_total=known_total):
                execution = self.execution(idle=RECENT)
                WorkflowExecution.objects.filter(pk=execution.pk).update(
                    total_files=known_total
                )
                self.file(execution, ExecutionStatus.COMPLETED, idle=RECENT)
                self.file(execution, ExecutionStatus.ERROR, idle=RECENT)
                self.file(execution, ExecutionStatus.EXECUTING, idle=RECENT)

                self._abort(self.owner, execution.id)

                execution.refresh_from_db()
                self.assertEqual(
                    (
                        execution.total_files,
                        execution.successful_files,
                        execution.failed_files,
                    ),
                    (total, 1, total - 1),
                )

    def test_abort_releases_the_slot_stamps_the_time_and_notifies_the_inbox(self) -> None:
        execution = self.execution(self.deployment())
        started = timezone.now() - timedelta(hours=1)
        WorkflowExecution.objects.filter(pk=execution.pk).update(created_at=started)
        with (
            patch(
                "api_v2.rate_limiter.APIDeploymentRateLimiter.release_slot"
            ) as release,
            patch("inbox.events.notify_execution_failed") as notify,
        ):
            self._abort(self.owner, execution.id)
        release.assert_called_once_with(self.org.organization_id, str(execution.id))
        notify.assert_called_once_with(execution.id)
        execution.refresh_from_db()
        self.assertAlmostEqual(execution.execution_time, 3600, delta=60)

    def _abort_with_notification_patched(self, execution: WorkflowExecution) -> Any:
        with patch("workflow_manager.execution.abort.PipelineNotification") as notify:
            self._abort(self.owner, execution.id)
        notify.return_value.send.assert_called_once()
        return notify.call_args.kwargs

    def test_abort_marks_the_pipeline_failed_and_notifies(self) -> None:
        for active in (True, False):
            with self.subTest(active=active):
                pipeline = self.pipeline()
                Pipeline.objects.filter(pk=pipeline.pk).update(active=active)
                execution = self.execution(pipeline)

                sent = self._abort_with_notification_patched(execution)

                pipeline.refresh_from_db()
                self.assertEqual(
                    pipeline.last_run_status, Pipeline.PipelineStatus.FAILURE
                )
                self.assertIsNotNone(pipeline.last_run_time)
                self.assertEqual(sent["execution_id"], execution.id)

    def test_a_failed_pipeline_save_still_notifies(self) -> None:
        execution = self.execution(self.pipeline())
        with (
            patch.object(Pipeline, "save", side_effect=RuntimeError("boom")),
            self.assertLogs("workflow_manager.execution.abort", level="ERROR") as logs,
        ):
            sent = self._abort_with_notification_patched(execution)

        self.assertEqual(sent["execution_id"], execution.id)
        self.assertIn(str(execution.id), logs.output[0])

    def test_abort_of_an_old_run_notifies_but_keeps_the_pipeline_status(self) -> None:
        pipeline = self.pipeline()
        old_run = self.execution(pipeline)
        self.execution(pipeline, status=ExecutionStatus.COMPLETED)
        Pipeline.objects.filter(pk=pipeline.pk).update(
            last_run_status=Pipeline.PipelineStatus.SUCCESS
        )

        sent = self._abort_with_notification_patched(old_run)

        self.assertEqual(sent["pipeline"].last_run_status, Pipeline.PipelineStatus.FAILURE)
        pipeline.refresh_from_db()
        self.assertEqual(pipeline.last_run_status, Pipeline.PipelineStatus.SUCCESS)
        self.assertIsNone(pipeline.last_run_time)

    def test_abort_of_a_deployment_run_notifies_the_deployment(self) -> None:
        execution = self.execution(self.deployment())
        with patch(
            "workflow_manager.execution.abort.APIDeploymentUtils.send_notification"
        ) as send:
            self._abort(self.owner, execution.id)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["workflow_execution"].id, execution.id)

    def test_finished_run_announces_nothing(self) -> None:
        execution = self.execution(self.pipeline(), status=ExecutionStatus.COMPLETED)
        with patch("workflow_manager.execution.abort._report_abort") as report:
            self._abort(self.owner, execution.id)
        report.assert_not_called()

    def test_abort_takes_one_row_lock(self) -> None:
        execution = self.execution()
        # The inbox notice takes its own lock on commit.
        with (
            patch("inbox.events.notify_execution_failed"),
            CaptureQueriesContext(connection) as queries,
        ):
            self._abort(self.owner, execution.id)
        lock_statements: Any = locking._lock_statements
        _, no_key, full = lock_statements(queries.captured_queries)
        self.assertEqual(len(no_key), 1)
        self.assertEqual(full, [])

    def test_aborting_twice_answers_already_finished(self) -> None:
        execution = self.execution()
        self._abort(self.owner, execution.id)
        outcome = self._outcomes(self._abort(self.owner, execution.id))
        self.assertEqual(outcome[str(execution.id)], ("already_finished", "STOPPED"))
        self.assertEqual(PlatformAuditEvent.objects.count(), 1)

    def test_one_failing_id_answers_failed_in_a_200(self) -> None:
        bad, good = self.execution(), self.execution()

        def stop(execution: WorkflowExecution) -> None:
            if execution.pk == bad.pk:
                raise RuntimeError("boom")

        with patch("workflow_manager.execution.abort._stop_open_files", side_effect=stop):
            response = self._abort(self.owner, bad.id, good.id)

        self.assertEqual(
            self._outcomes(response),
            {str(bad.id): ("failed", None), str(good.id): ("aborted", "STOPPED")},
        )
        self.assertEqual((response.data["aborted"], response.data["failed"]), (1, 1))

    def test_abort_is_audited(self) -> None:
        deployment = self.deployment()
        execution = self.execution(deployment)

        self._abort(self.owner, execution.id)

        event = PlatformAuditEvent.objects.get(action=Action.EXECUTION_ABORTED)
        self.assertEqual(event.organization, self.org)
        self.assertEqual(event.actor, self.owner)
        self.assertEqual(event.target_type, TargetType.EXECUTION)
        self.assertEqual(event.target_id, str(execution.id))
        self.assertEqual(event.target_name, self.workflow.workflow_name)
        self.assertEqual(event.summary, "was EXECUTING")
        self.assertEqual(
            event.metadata,
            {
                "previous_status": "EXECUTING",
                "pipeline_id": str(deployment.id),
                "entity": "API",
            },
        )

    def test_finished_run_is_already_finished_and_not_audited(self) -> None:
        execution = self.execution(status=ExecutionStatus.COMPLETED)
        response = self._abort(self.owner, execution.id)
        self.assertEqual(
            self._outcomes(response),
            {str(execution.id): ("already_finished", "COMPLETED")},
        )
        self.assertEqual(self._status(execution), ExecutionStatus.COMPLETED.value)
        self.assertFalse(PlatformAuditEvent.objects.exists())

    def test_mixed_batch_answers_each_id_in_one_200(self) -> None:
        mine = self.execution(self.pipeline())
        finished = self.execution(status=ExecutionStatus.ERROR)
        other = _make_user("other@example.com")
        foreign_workflow_run = self._run_owned_by(other)
        unknown = uuid.uuid4()

        response = self._abort(
            self.owner, mine.id, finished.id, foreign_workflow_run.id, unknown
        )

        self.assertEqual(
            self._outcomes(response),
            {
                str(mine.id): ("aborted", "STOPPED"),
                str(finished.id): ("already_finished", "ERROR"),
                str(foreign_workflow_run.id): ("not_permitted", None),
                str(unknown): ("not_permitted", None),
            },
        )
        self.assertEqual(
            [r["id"] for r in response.data["results"]],
            [str(mine.id), str(finished.id), str(foreign_workflow_run.id), str(unknown)],
        )
        self.assertEqual(
            (
                response.data["aborted"],
                response.data["already_finished"],
                response.data["not_permitted"],
            ),
            (1, 1, 2),
        )
        self.assertEqual(
            self._status(foreign_workflow_run), ExecutionStatus.EXECUTING.value
        )

    def _run_owned_by(self, user: Any) -> WorkflowExecution:
        """A run of a deployment ``user`` owns, which ``self.owner`` only sees."""
        deployment = self.deployment()
        deployment.memberships.filter(user=self.owner).delete()
        deployment.memberships.create(user=user, role=ResourceRole.OWNER)
        _add_viewers(deployment, self.owner)
        return self.execution(deployment)

    def test_another_orgs_run_is_not_permitted_for_admin_or_service_account(self) -> None:
        other_org = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        other_workflow = Workflow.objects.create(
            workflow_name="wf-b", organization=other_org, created_by=self.owner
        )
        foreign = WorkflowExecution.objects.create(
            workflow=other_workflow,
            execution_mode=WorkflowExecution.Mode.QUEUE,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.EXECUTING.value,
            queue_message_id=1,
        )
        service = _make_user("svc@example.com", is_service_account=True)

        for user in (self.admin, service):
            with self.subTest(user=user.email):
                outcome = self._outcomes(self._abort(user, foreign.id))
                self.assertEqual(outcome[str(foreign.id)], ("not_permitted", None))

        self.assertEqual(self._status(foreign), ExecutionStatus.EXECUTING.value)
        self.assertFalse(PlatformAuditEvent.objects.exists())

    def test_shared_viewer_is_not_permitted(self) -> None:
        deployment = self.deployment()
        _add_viewers(deployment, self.outsider)
        execution = self.execution(deployment)
        # Control: the viewer can see the run.
        self.assertTrue(
            WorkflowExecution.objects.for_user(self.outsider)
            .filter(pk=execution.pk)
            .exists()
        )

        response = self._abort(self.outsider, execution.id)

        self.assertEqual(
            self._outcomes(response), {str(execution.id): ("not_permitted", None)}
        )
        self.assertEqual(self._status(execution), ExecutionStatus.EXECUTING.value)

    def test_workflow_owner_cannot_abort_a_pipeline_run_they_do_not_own(self) -> None:
        pipeline = self.pipeline()
        pipeline.memberships.filter(user=self.owner).delete()
        Pipeline.objects.filter(pk=pipeline.pk).update(shared_to_org=True)
        execution = self.execution(pipeline)
        outcome = self._outcomes(self._abort(self.owner, execution.id))
        self.assertEqual(outcome[str(execution.id)][0], "not_permitted")

    def test_co_owner_of_the_workflow_aborts_a_workflow_run(self) -> None:
        self.workflow.memberships.create(user=self.member, role=ResourceRole.OWNER)
        execution = self.execution(status=ExecutionStatus.PENDING)
        outcome = self._outcomes(self._abort(self.member, execution.id))
        self.assertEqual(outcome[str(execution.id)], ("aborted", "STOPPED"))

    def test_org_admin_can_abort_any_run(self) -> None:
        execution = self.execution(self.deployment())
        outcome = self._outcomes(self._abort(self.admin, execution.id))
        self.assertEqual(outcome[str(execution.id)], ("aborted", "STOPPED"))
        event = PlatformAuditEvent.objects.get(action=Action.EXECUTION_ABORTED)
        self.assertEqual(event.actor, self.admin)

    def test_service_account_can_abort(self) -> None:
        service = _make_user("svc@example.com", is_service_account=True)
        execution = self.execution(self.pipeline())
        outcome = self._outcomes(self._abort(service, execution.id))
        self.assertEqual(outcome[str(execution.id)], ("aborted", "STOPPED"))

    def test_duplicate_ids_are_answered_once(self) -> None:
        execution = self.execution()
        response = self._abort(self.owner, execution.id, execution.id)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(PlatformAuditEvent.objects.count(), 1)

    def test_invalid_bodies_are_400(self) -> None:
        self.assertEqual(MAX_ABORT_IDS, 100)
        too_many = [str(uuid.uuid4()) for _ in range(101)]
        bodies: list[dict[str, Any]] = [
            {},
            {"ids": []},
            {"ids": ["not-a-uuid"]},
            {"ids": too_many},
        ]
        for body in bodies:
            with self.subTest(body=body):
                response = self._abort(self.owner, raw=body)
                self.assertEqual(response.status_code, 400)

    def test_requires_authentication(self) -> None:
        request = self.factory.post("/", {"ids": [str(uuid.uuid4())]}, format="json")
        response = _abort(request)
        self.assertIn(response.status_code, (401, 403))

    def test_later_writes_cannot_undo_the_abort(self) -> None:
        # Scheduled and API-triggered pipeline runs have no queue_message_id.
        for queue_message_id in (1, None):
            for status in (ExecutionStatus.COMPLETED, ExecutionStatus.ERROR):
                with self.subTest(queue_message_id=queue_message_id, status=status):
                    execution = self.execution(
                        self.pipeline(), queue_message_id=queue_message_id
                    )
                    self._abort(self.owner, execution.id)

                    out = self._write_status(execution, {"status": status.value})

                    self.assertEqual(out.data.get("reason"), "already_final")
                    self.assertEqual(out.data.get("new_status"), "STOPPED")
                    self.assertEqual(
                        self._status(execution), ExecutionStatus.STOPPED.value
                    )

    def test_backend_writes_before_dispatch_cannot_undo_the_abort(self) -> None:
        # Staging or dispatch fails, or stages nothing, after a PENDING run's abort.
        helper = WorkflowExecutionServiceHelper
        writes: dict[str, Callable[[str], Any]] = {
            "error": lambda pk: helper.update_execution_err(pk, "staging failed"),
            "completed": lambda pk: helper.update_execution_completed(pk, 2, 2),
        }
        for name, write in writes.items():
            with self.subTest(write=name):
                execution = self.execution(
                    self.deployment(),
                    status=ExecutionStatus.PENDING,
                    queue_message_id=None,
                )
                self._abort(self.owner, execution.id)

                write(str(execution.pk))

                execution.refresh_from_db()
                self.assertEqual(execution.status, ExecutionStatus.STOPPED.value)
                self.assertEqual((execution.total_files, execution.failed_files), (0, 0))

    @staticmethod
    def _write_status(execution: WorkflowExecution, data: dict[str, Any]) -> Any:
        """A worker's status write through the internal API."""
        view = WorkflowExecutionInternalViewSet()
        request = MagicMock()
        request.data = data
        fresh = WorkflowExecution.objects.get(pk=execution.pk)
        with patch.object(view, "get_object", return_value=fresh):
            return view.update_status(request, id=str(execution.id))

    def test_a_stopped_write_saves_the_counts_of_the_file_rows(self) -> None:
        execution = self.execution(self.pipeline())
        for status in (ExecutionStatus.COMPLETED, ExecutionStatus.COMPLETED):
            self.file(execution, status, idle=RECENT)
        in_flight = self.file(execution, ExecutionStatus.EXECUTING, idle=RECENT)
        self._abort(self.owner, execution.id)
        # The file in progress at the abort finishes afterwards.
        WorkflowFileExecution.objects.filter(pk=in_flight.pk).update(
            status=ExecutionStatus.COMPLETED.value
        )

        # The worker reports zeros, as a failed callback's retry does.
        out = self._write_status(
            execution,
            {
                "status": ExecutionStatus.STOPPED.value,
                "total_files": 0,
                "successful_files": 0,
                "failed_files": 0,
            },
        )

        self.assertEqual(out.data.get("status"), "updated")
        execution.refresh_from_db()
        self.assertEqual(
            (
                execution.total_files,
                execution.successful_files,
                execution.failed_files,
            ),
            (3, 3, 0),
        )
