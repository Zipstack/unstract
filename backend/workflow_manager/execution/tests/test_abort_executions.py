"""``POST execution/abort/`` (UN-4318): owner-or-admin, per-id outcomes, audit."""

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from platform_audit.actions import Action, TargetType
from platform_audit.models import PlatformAuditEvent
from tenant_account_v2.tests import _add_viewers, _make_user

from workflow_manager.execution.abort import ABORT_ERROR_MESSAGE, MAX_ABORT_IDS
from workflow_manager.execution.tests.stuck_abort_base import RECENT, StuckAbortTestBase
from workflow_manager.execution.views import ExecutionAbortView
from workflow_manager.internal_views import WorkflowExecutionInternalViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

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
        ):
            row.refresh_from_db()
            self.assertEqual(row.status, expected.value)
        done.refresh_from_db()
        self.assertIsNone(done.execution_error)

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
        too_many = [str(uuid.uuid4()) for _ in range(MAX_ABORT_IDS + 1)]
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

    def test_later_completion_cannot_undo_the_abort(self) -> None:
        execution = self.execution(self.pipeline())
        self._abort(self.owner, execution.id)

        view = WorkflowExecutionInternalViewSet()
        request = MagicMock()
        request.data = {"status": ExecutionStatus.COMPLETED.value}
        fresh = WorkflowExecution.objects.get(pk=execution.pk)
        with patch.object(view, "get_object", return_value=fresh):
            out = view.update_status(request, id=str(execution.id))

        self.assertEqual(out.data.get("reason"), "already_final")
        self.assertEqual(self._status(execution), ExecutionStatus.STOPPED.value)
