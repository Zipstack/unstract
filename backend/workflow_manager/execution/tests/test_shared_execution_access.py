"""Executions and their logs follow the sharing paths of the resource they belong
to — memberships, group shares and ``shared_to_org`` (UN-2651).
"""

import secrets
from unittest.mock import patch

from api_v2.models import APIDeployment
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory
from tenant_account_v2.models import ResourceGroupShare
from tenant_account_v2.tests import GroupSharingTestBase

from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.execution_log_view import WorkflowExecutionLogViewSet
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog

_ADMIN_PREDICATE = (
    "tenant_account_v2.organization_member_service."
    "OrganizationMemberService.is_user_organization_admin"
)


class SharedExecutionAccessTests(GroupSharingTestBase):
    """``self.member`` belongs to ``self.group``; ``self.outsider`` is an org
    member with no share of any kind. Neither owns anything here.
    """

    def setUp(self) -> None:
        super().setUp()
        # Pin admin resolution: "admins see everything" would mask the paths here.
        patcher = patch(_ADMIN_PREDICATE, return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _api_deployment(self, *, shared_to_org: bool = False) -> APIDeployment:
        # api_name must be short — it defaults to a UUID longer than the column.
        return APIDeployment.objects.create(
            api_name=f"api-{secrets.token_hex(4)}",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            shared_to_org=shared_to_org,
        )

    def _execution(self, deployment: APIDeployment) -> WorkflowExecution:
        return WorkflowExecution.objects.create(
            workflow=self.workflow,
            pipeline_id=deployment.id,
            execution_mode=WorkflowExecution.Mode.INSTANT,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.COMPLETED,
        )

    def _share_with_group(self, deployment: APIDeployment) -> None:
        ResourceGroupShare.objects.create(
            group=self.group,
            content_type=ContentType.objects.get_for_model(APIDeployment),
            object_id=str(deployment.id),
            organization=self.org,
        )

    def _visible_to(self, user, execution: WorkflowExecution) -> bool:
        return (
            WorkflowExecution.objects.for_user(user).filter(pk=execution.pk).exists()
        )

    def _log_queryset(self, user, execution_id):
        """Run the log viewset's queryset build for ``user`` — the access gate."""
        request = APIRequestFactory().get("/")
        request.user = user
        view = WorkflowExecutionLogViewSet()
        view.request = request
        view.kwargs = {"pk": str(execution_id)}
        return view.get_queryset()

    def test_org_wide_share_exposes_the_deployment_executions(self) -> None:
        execution = self._execution(self._api_deployment(shared_to_org=True))
        self.assertTrue(self._visible_to(self.outsider, execution))

    def test_group_share_exposes_the_deployment_executions(self) -> None:
        deployment = self._api_deployment()
        self._share_with_group(deployment)
        execution = self._execution(deployment)

        self.assertTrue(self._visible_to(self.member, execution))
        # Same org, not in the group — still nothing.
        self.assertFalse(self._visible_to(self.outsider, execution))

    def test_unshared_deployment_stays_invisible(self) -> None:
        execution = self._execution(self._api_deployment())
        self.assertFalse(self._visible_to(self.outsider, execution))

    def test_logs_denied_when_the_execution_is_not_accessible(self) -> None:
        execution = self._execution(self._api_deployment())
        with self.assertRaises(PermissionDenied):
            self._log_queryset(self.outsider, execution.id)

    def test_logs_readable_once_the_deployment_is_shared(self) -> None:
        execution = self._execution(self._api_deployment(shared_to_org=True))
        log = ExecutionLog.objects.create(
            wf_execution=execution, data={"log": "hello"}, event_time=timezone.now()
        )
        self.assertIn(log, list(self._log_queryset(self.outsider, execution.id)))
