"""Fixtures for the stuck-execution and abort tests (UN-4318).

``self.owner`` owns the workflow, deployments and pipelines built here;
``self.admin`` is the only org admin; ``self.outsider`` has no share.
"""

import secrets
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from api_v2.models import APIDeployment
from django.utils import timezone
from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.tests import GroupSharingTestBase

from workflow_manager.file_execution.models import WorkflowFileExecution
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution

ADMIN_PREDICATE = (
    "tenant_account_v2.organization_member_service."
    "OrganizationMemberService.is_user_organization_admin"
)
# Past the default 9000 s threshold, and well inside it.
OLD = timedelta(hours=3)
RECENT = timedelta(minutes=1)


class StuckAbortTestBase(GroupSharingTestBase):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch(
            ADMIN_PREDICATE,
            side_effect=lambda user: getattr(user, "email", None) == self.admin.email,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.factory = APIRequestFactory()

    def deployment(self) -> APIDeployment:
        deployment: APIDeployment = APIDeployment.objects.create(
            api_name=f"api-{secrets.token_hex(4)}",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
        )
        deployment.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        return deployment

    def pipeline(self, pipeline_type: Any = Pipeline.PipelineType.ETL) -> Pipeline:
        pipeline: Pipeline = Pipeline.objects.create(
            pipeline_name=f"pipe-{secrets.token_hex(4)}",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            pipeline_type=pipeline_type,
        )
        pipeline.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        return pipeline

    def execution(
        self,
        resource: Any = None,
        status: ExecutionStatus = ExecutionStatus.EXECUTING,
        idle: timedelta = OLD,
    ) -> WorkflowExecution:
        """A PG-transport run whose last own write was ``idle`` ago."""
        execution: WorkflowExecution = WorkflowExecution.objects.create(
            workflow=self.workflow,
            pipeline_id=resource.id if resource else None,
            execution_mode=WorkflowExecution.Mode.QUEUE,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=status.value,
            queue_message_id=1,
        )
        self.backdate(WorkflowExecution, execution.pk, idle)
        execution.refresh_from_db()
        return execution

    def file(
        self, execution: WorkflowExecution, status: ExecutionStatus, idle: timedelta
    ) -> WorkflowFileExecution:
        row: WorkflowFileExecution = WorkflowFileExecution.objects.create(
            workflow_execution=execution, file_name="f.pdf", status=status.value
        )
        self.backdate(WorkflowFileExecution, row.pk, idle)
        row.refresh_from_db()
        return row

    @staticmethod
    def backdate(model: Any, pk: Any, idle: timedelta) -> None:
        # update() skips auto_now, so modified_at keeps the backdated value.
        model.objects.filter(pk=pk).update(modified_at=timezone.now() - idle)

    def call(
        self,
        view: Any,
        user: Any,
        method: str = "get",
        data: Any = None,
        **url_kwargs: Any,
    ) -> Any:
        """Run ``view`` as ``user`` and every on-commit callback it registers."""
        if method == "get":
            request = self.factory.get("/", data or {})
        else:
            request = self.factory.post("/", data, format="json")
        force_authenticate(request, user=user)
        with self.captureOnCommitCallbacks(execute=True):
            response = view(request, **url_kwargs)
        response.render()
        return response
