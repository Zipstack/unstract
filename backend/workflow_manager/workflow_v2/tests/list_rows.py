"""Seed helpers for the deployment and pipeline list filter and aggregate tests."""

import uuid
from datetime import timedelta
from typing import Any

from account_v2.models import Organization, User
from api_v2.models import APIDeployment
from django.utils import timezone
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin
from pipeline_v2.models import Pipeline
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from utils.user_context import UserContext

from unstract.core.data_models import ExecutionStatus
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.workflow import Workflow

ERROR = ExecutionStatus.ERROR.value
COMPLETED = ExecutionStatus.COMPLETED.value
STOPPED = ExecutionStatus.STOPPED.value
PENDING = ExecutionStatus.PENDING.value
EXECUTING = ExecutionStatus.EXECUTING.value

FIVE_ERRORS = [ERROR] * 5


class ListRowsSeed(CoOwnerOrgTestMixin):
    """An org with members, a second org, and builders for rows and their runs."""

    def setUp(self) -> None:
        self._seed_org()
        self.now = timezone.now().replace(microsecond=0)
        self.org_b = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )

    def tearDown(self) -> None:
        # Left set, this thread-local scopes the managers in whatever runs next.
        UserContext.set_organization_identifier(None)  # type: ignore[arg-type]

    def _workflow(self, org: Organization | None = None) -> Workflow:
        workflow: Workflow = Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:8]}",
            organization=org or self.org,
            created_by=self.owner,
        )
        return workflow

    def _deployment(
        self,
        name: str,
        org: Organization | None = None,
        owner: User | None = None,
        **fields: Any,
    ) -> APIDeployment:
        row: APIDeployment = APIDeployment.objects.create(
            api_name=f"api-{uuid.uuid4().hex[:8]}",
            display_name=name,
            workflow=self._workflow(org),
            organization=org or self.org,
            created_by=self.owner,
            **fields,
        )
        row.grant_owner(owner or self.owner)
        return row

    def _pipeline(
        self,
        name: str,
        pipeline_type: str = "ETL",
        org: Organization | None = None,
        owner: User | None = None,
        **fields: Any,
    ) -> Pipeline:
        row: Pipeline = Pipeline.objects.create(
            pipeline_name=name,
            pipeline_type=pipeline_type,
            workflow=self._workflow(org),
            organization=org or self.org,
            created_by=self.owner,
            active=fields.pop("active", True),
            **fields,
        )
        row.grant_owner(owner or self.owner)
        return row

    def _share(self, row: Any, user: User) -> None:
        row.memberships.create(user=user, role=ResourceRole.VIEWER)

    def _runs(
        self,
        row: Any,
        statuses_oldest_first: list[str],
        hours_ago: int = 10,
        **fields: Any,
    ) -> None:
        """One run per status, an hour apart, the oldest ``hours_ago`` hours ago."""
        # bulk_create skips the post-save hooks, which reach Redis.
        runs = WorkflowExecution.objects.bulk_create(
            [
                WorkflowExecution(
                    workflow=row.workflow, pipeline_id=row.pk, status=status, **fields
                )
                for status in statuses_oldest_first
            ]
        )
        for offset, run in enumerate(runs):
            WorkflowExecution.objects.filter(pk=run.pk).update(
                created_at=self.now - timedelta(hours=hours_ago - offset)
            )

    def _call(
        self, view: Any, action: str, user: User, url: str, **params: Any
    ) -> Response:
        request = APIRequestFactory().get(url, params)
        force_authenticate(request, user=user)
        response: Response = view.as_view({"get": action})(request)
        return response
