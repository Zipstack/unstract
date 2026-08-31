"""Integration tests for direct-user share/revoke email wiring (UN-3494).

The ``share/`` endpoint's ``shared_users`` axis mails users who gained or lost
direct access. Both notification seams are mocked, so these pin the wiring and
the payload — who is mailed, with what, and that a failing send never breaks a
share that already committed — not template or transport behavior. The group
axis is covered by ``ResourceShareNotificationTests`` in
``tenant_account_v2.tests``.

DB-backed (Django ``TestCase``), so ``backend/conftest.py`` auto-marks these
``integration`` and the rig runs them in ``integration-backend``.
"""

from unittest.mock import Mock, patch

from account_v2.models import User
from django.test import TestCase
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet

from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin


class DirectShareNotificationWiringTests(CoOwnerOrgTestMixin, TestCase):
    """``POST share/`` mails users whose direct access was granted or revoked."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-1", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.factory = APIRequestFactory()
        self.service = Mock()
        plugin = {"service_class": Mock(return_value=self.service)}
        for p in (
            # The sender lives in the share mixin; ``_notification_context``
            # gates on the membership_views copy, so both need the plugin.
            patch("permissions.resource_share_views.notification_plugin", plugin),
            patch("permissions.membership_views.notification_plugin", plugin),
            patch.object(
                WorkflowViewSet,
                "get_notification_resource_type",
                return_value="workflow",
            ),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _share(self, actor: User, payload: dict) -> Response:
        view = WorkflowViewSet.as_view({"post": "share"})
        request = self.factory.post("/x/", payload, format="json")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.workflow.pk))

    def test_granting_direct_access_fires_sharing_notification(self) -> None:
        response = self._share(self.owner, {"shared_users": [self.viewer.pk]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.send_sharing_notification.assert_called_once()
        kwargs = self.service.send_sharing_notification.call_args.kwargs
        self.assertEqual(kwargs["resource_type"], "workflow")
        self.assertEqual(kwargs["resource_name"], "wf-1")
        self.assertEqual(kwargs["resource_id"], str(self.workflow.pk))
        self.assertEqual(kwargs["shared_by"], self.owner)
        self.assertEqual([u.pk for u in kwargs["shared_to"]], [self.viewer.pk])
        self.assertEqual(kwargs["resource_instance"], self.workflow)
        self.service.send_access_removed_notification.assert_not_called()

    def test_revoking_direct_access_fires_access_removed_notification(self) -> None:
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        response = self._share(self.owner, {"shared_users": []})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.send_access_removed_notification.assert_called_once()
        kwargs = self.service.send_access_removed_notification.call_args.kwargs
        self.assertEqual(kwargs["resource_type"], "workflow")
        self.assertEqual([u.pk for u in kwargs["removed_from"]], [self.viewer.pk])
        self.assertEqual(kwargs["removed_by"], self.owner)
        self.assertEqual(kwargs["resource_id"], str(self.workflow.pk))
        self.service.send_sharing_notification.assert_not_called()

    def test_revoke_is_silent_when_the_user_keeps_access_another_way(self) -> None:
        # Dropped from ``shared_users`` but still covered by the org-wide share —
        # nothing was lost, so telling them it was removed would be wrong.
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        response = self._share(self.owner, {"shared_users": [], "shared_to_org": True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.send_access_removed_notification.assert_not_called()

    def test_notification_failure_does_not_break_the_share(self) -> None:
        # The share commits before the mail goes out; a raising sender must not
        # surface as a 500 on a share that succeeded.
        self.service.send_sharing_notification.side_effect = RuntimeError("boom")
        response = self._share(self.owner, {"shared_users": [self.viewer.pk]})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        viewer_ids = set(
            self.workflow.memberships.filter(role=ResourceRole.VIEWER).values_list(
                "user_id", flat=True
            )
        )
        self.assertIn(self.viewer.pk, viewer_ids)
