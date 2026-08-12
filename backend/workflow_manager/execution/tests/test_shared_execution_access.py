"""Executions and their logs follow the sharing paths of the resource they belong
to — memberships, group shares and ``shared_to_org`` (UN-2651).
"""

import secrets
import uuid
from unittest.mock import patch

from account_v2.models import Organization
from api_v2.models import APIDeployment
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from permissions.roles import ResourceRole
from pipeline_v2.models import Pipeline
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import ResourceGroupShare
from tenant_account_v2.tests import GroupSharingTestBase, _add_viewers, _make_user
from utils.user_context import UserContext

from workflow_manager.file_execution.views import FileCentricExecutionViewSet
from workflow_manager.workflow_v2.enums import ExecutionStatus
from workflow_manager.workflow_v2.execution_log_view import WorkflowExecutionLogViewSet
from workflow_manager.workflow_v2.execution_view import WorkflowExecutionViewSet
from workflow_manager.workflow_v2.models.execution import WorkflowExecution
from workflow_manager.workflow_v2.models.execution_log import ExecutionLog
from workflow_manager.workflow_v2.models.workflow import Workflow

_ADMIN_PREDICATE = (
    "tenant_account_v2.organization_member_service."
    "OrganizationMemberService.is_user_organization_admin"
)


class SharedExecutionAccessTests(GroupSharingTestBase):
    """``self.member`` belongs to ``self.group``; ``self.outsider`` is an org
    member with no share of any kind. ``self.owner`` owns every fixture in org A
    (the cross-org test builds its own, deliberately unowned).
    """

    def setUp(self) -> None:
        super().setUp()
        # Pin admin resolution: "admins see everything" would mask the paths here.
        patcher = patch(_ADMIN_PREDICATE, return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _api_deployment(self, *, shared_to_org: bool = False) -> APIDeployment:
        # api_name must be short — it defaults to a UUID longer than the column.
        deployment = APIDeployment.objects.create(
            api_name=f"api-{secrets.token_hex(4)}",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            shared_to_org=shared_to_org,
        )
        # Creator access flows through an OWNER row, not ``created_by`` (UN-2202);
        # mirrors what ``APIDeploymentViewSet.create`` does after ``perform_create``.
        deployment.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        return deployment

    def _pipeline(self, *, shared_to_org: bool = False) -> Pipeline:
        pipeline = Pipeline.objects.create(
            pipeline_name=f"pipe-{secrets.token_hex(4)}",
            workflow=self.workflow,
            organization=self.org,
            created_by=self.owner,
            shared_to_org=shared_to_org,
        )
        pipeline.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        return pipeline

    def _execution(self, resource=None) -> WorkflowExecution:
        """``resource=None`` builds a workflow-level execution (``pipeline_id``
        NULL), which is the only shape that exercises the workflow branch of
        ``for_user``.
        """
        return WorkflowExecution.objects.create(
            workflow=self.workflow,
            pipeline_id=resource.id if resource else None,
            execution_mode=WorkflowExecution.Mode.INSTANT,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.COMPLETED,
        )

    def _share_with_group(self, resource) -> None:
        ResourceGroupShare.objects.create(
            group=self.group,
            content_type=ContentType.objects.get_for_model(type(resource)),
            object_id=str(resource.pk),
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

    def _call(self, action: str, user, execution_id, **query):
        """Drive the real endpoint, so ``dispatch`` translates the gate to HTTP."""
        view = WorkflowExecutionLogViewSet.as_view({"get": action})
        request = APIRequestFactory().get("/", query)
        force_authenticate(request, user=user)
        return view(request, pk=str(execution_id))

    # --- visibility: who sees which executions ---------------------------------

    def test_unshared_deployment_is_visible_only_to_its_owner(self) -> None:
        execution = self._execution(self._api_deployment())
        # The owner assertion is what makes the denial below a real control:
        # without the OWNER membership row the deployment would be visible to
        # nobody, and the denial would pass with the sharing filter deleted.
        self.assertTrue(self._visible_to(self.owner, execution))
        self.assertFalse(self._visible_to(self.outsider, execution))

    def test_direct_viewer_sees_the_deployment_executions(self) -> None:
        deployment = self._api_deployment()
        _add_viewers(deployment, self.outsider)
        self.assertTrue(self._visible_to(self.outsider, self._execution(deployment)))

    def test_co_owner_sees_the_deployment_executions(self) -> None:
        deployment = self._api_deployment()
        deployment.memberships.create(user=self.member, role=ResourceRole.OWNER)
        self.assertTrue(self._visible_to(self.member, self._execution(deployment)))

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

    def test_workflow_level_execution_follows_the_workflow_share(self) -> None:
        execution = self._execution()  # pipeline_id NULL
        self.assertTrue(self._visible_to(self.owner, execution))
        self.assertFalse(self._visible_to(self.member, execution))

        self._share_with_group(self.workflow)
        self.assertTrue(self._visible_to(self.member, execution))
        self.assertFalse(self._visible_to(self.outsider, execution))

    def test_pipeline_execution_follows_the_pipeline_share(self) -> None:
        private = self._execution(self._pipeline())
        self.assertTrue(self._visible_to(self.owner, private))
        self.assertFalse(self._visible_to(self.outsider, private))

        shared = self._execution(self._pipeline(shared_to_org=True))
        self.assertTrue(self._visible_to(self.outsider, shared))

    def test_workflow_share_does_not_expose_unshared_deployment_runs(self) -> None:
        """Pins the ``pipeline_id__isnull=True`` conjunct on the workflow branch.

        Workflow access must not leak into runs of a deployment that was
        deliberately not shared — the "every path has to be revoked" behaviour.
        """
        deployment = self._api_deployment()  # shared with nobody
        execution = self._execution(deployment)
        self._share_with_group(self.workflow)

        self.assertIn(self.workflow, Workflow.objects.for_user(self.member))
        self.assertFalse(self._visible_to(self.member, execution))

    def test_deployment_share_does_not_expose_workflow_level_runs(self) -> None:
        """The other half: a deployment share says nothing about the workflow's
        own runs, which is why the two branches are not symmetric.
        """
        deployment = self._api_deployment(shared_to_org=True)
        self.assertTrue(self._visible_to(self.outsider, self._execution(deployment)))
        self.assertFalse(self._visible_to(self.outsider, self._execution()))

    def test_org_wide_share_does_not_cross_organizations(self) -> None:
        """``shared_to_org`` means *this* org — the tenant boundary for
        ``/execution/`` is the manager, since the view drops the org filter
        backend.
        """
        other_org = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        other_workflow = Workflow.objects.create(
            workflow_name="wf-b", organization=other_org, created_by=self.owner
        )
        foreign = APIDeployment.objects.create(
            api_name=f"api-{secrets.token_hex(4)}",
            workflow=other_workflow,
            organization=other_org,
            created_by=self.owner,
            shared_to_org=True,
        )
        execution = WorkflowExecution.objects.create(
            workflow=other_workflow,
            pipeline_id=foreign.id,
            execution_mode=WorkflowExecution.Mode.INSTANT,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.COMPLETED,
        )

        # Control: the same shape inside org A *is* visible, so the denial below
        # is about the org boundary and not about the fixture being malformed.
        local = self._execution(self._api_deployment(shared_to_org=True))
        self.assertTrue(self._visible_to(self.outsider, local))

        # UserContext still points at org A throughout.
        self.assertFalse(self._visible_to(self.outsider, execution))
        with self.assertRaises(PermissionDenied):
            self._log_queryset(self.outsider, execution.id)

    # --- the log endpoints ------------------------------------------------------

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

    def test_both_endpoints_return_403_for_an_inaccessible_execution(self) -> None:
        execution = self._execution(self._api_deployment())
        for action in ("list", "export"):
            with self.subTest(action=action):
                response = self._call(action, self.outsider, execution.id)
                self.assertEqual(response.status_code, 403)

    def test_both_endpoints_serve_a_shared_execution(self) -> None:
        execution = self._execution(self._api_deployment(shared_to_org=True))
        ExecutionLog.objects.create(
            wf_execution=execution, data={"log": "hello"}, event_time=timezone.now()
        )

        listed = self._call("list", self.outsider, execution.id)
        self.assertEqual(listed.status_code, 200)
        listed.render()
        self.assertIn(b"hello", listed.content)

        exported = self._call(
            "export", self.outsider, execution.id, file_format="csv"
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn(b"hello", exported.content)

    def test_unknown_execution_is_indistinguishable_from_an_inaccessible_one(
        self,
    ) -> None:
        """An enumerator observes the response, not the exception — so the
        status and body must match, not merely the exception type.
        """
        inaccessible = self._execution(self._api_deployment())
        denied = self._call("list", self.outsider, inaccessible.id)
        unknown = self._call("list", self.outsider, uuid.uuid4())

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(unknown.status_code, denied.status_code)
        self.assertEqual(unknown.data, denied.data)

    # --- the sibling routes on the same execution id ---------------------------

    def _call_files(self, user, execution_id):
        view = FileCentricExecutionViewSet.as_view({"get": "list"})
        request = APIRequestFactory().get("/")
        force_authenticate(request, user=user)
        return view(request, pk=str(execution_id))

    def test_file_executions_follow_the_same_gate_as_the_logs(self) -> None:
        """``<id>/files/`` carries file names, per-file errors and the latest log
        line for the same id — 403 on logs and 200 here would defeat the point.
        """
        execution = self._execution(self._api_deployment())
        self.assertEqual(self._call_files(self.outsider, execution.id).status_code, 403)

        shared = self._execution(self._api_deployment(shared_to_org=True))
        self.assertEqual(self._call_files(self.outsider, shared.id).status_code, 200)

    def test_workflow_execution_list_is_scoped_to_accessible_workflows(self) -> None:
        """``/workflow/<id>/execution/`` had the same dead ``IsOwner`` gate."""
        execution = self._execution()  # workflow-level, owner-only

        view = WorkflowExecutionViewSet.as_view({"get": "list"})
        request = APIRequestFactory().get("/")
        force_authenticate(request, user=self.outsider)
        response = view(request, pk=str(self.workflow.id))
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(str(execution.id).encode(), response.content)


class ExecutionBypassRoleTests(GroupSharingTestBase):
    """The two branches that skip sharing entirely.

    The admin predicate is patched to a deterministic one — only ``self.admin``
    — rather than left to resolve for real: the admin *role string* belongs to
    the active authentication plugin (OSS reads ``"admin"``, the auth0 plugin
    reads ``"unstract_admin"``), so a test that depended on it would pass in OSS
    CI and fail on any checkout carrying the plugin. What is under test here is
    what ``for_user`` does once the predicate is True.
    """

    def setUp(self) -> None:
        super().setUp()
        patcher = patch(
            _ADMIN_PREDICATE,
            side_effect=lambda user: getattr(user, "email", None) == self.admin.email,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _execution(self) -> WorkflowExecution:
        return WorkflowExecution.objects.create(
            workflow=self.workflow,
            execution_mode=WorkflowExecution.Mode.INSTANT,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.COMPLETED,
        )

    def _visible_to(self, user, execution) -> bool:
        return WorkflowExecution.objects.for_user(user).filter(pk=execution.pk).exists()

    def test_org_admin_sees_executions_of_workflows_never_shared_with_them(self) -> None:
        execution = self._execution()
        self.assertTrue(self._visible_to(self.admin, execution))
        # Control: same user, non-admin role → back to the sharing rules.
        self.assertFalse(self._visible_to(self.outsider, execution))

    def test_service_account_sees_executions_without_any_membership(self) -> None:
        service = _make_user("svc@example.com", is_service_account=True)
        self.assertTrue(self._visible_to(service, self._execution()))

    def test_bypass_roles_stay_inside_the_current_organization(self) -> None:
        """The org filter in ``_org_scoped`` is the only tenant boundary these
        two branches have — the view drops ``OrganizationFilterBackend``.
        """
        other_org = Organization.objects.create(
            name="org-c", display_name="Org C", organization_id="org-c"
        )
        other_workflow = Workflow.objects.create(
            workflow_name="wf-c", organization=other_org, created_by=self.owner
        )
        foreign = WorkflowExecution.objects.create(
            workflow=other_workflow,
            execution_mode=WorkflowExecution.Mode.INSTANT,
            execution_method=WorkflowExecution.Method.DIRECT,
            execution_type=WorkflowExecution.Type.COMPLETE,
            status=ExecutionStatus.COMPLETED,
        )
        service = _make_user("svc2@example.com", is_service_account=True)

        # Control first: the local execution is visible to both bypass roles.
        local = self._execution()
        self.assertTrue(self._visible_to(self.admin, local))
        self.assertTrue(self._visible_to(service, local))

        self.assertFalse(self._visible_to(self.admin, foreign))
        self.assertFalse(self._visible_to(service, foreign))

    def test_no_organization_in_context_returns_nothing(self) -> None:
        """Fail closed rather than returning every tenant's executions."""
        execution = self._execution()
        UserContext.set_organization_identifier(None)
        self.addCleanup(
            UserContext.set_organization_identifier, self.org.organization_id
        )

        self.assertFalse(self._visible_to(self.admin, execution))
