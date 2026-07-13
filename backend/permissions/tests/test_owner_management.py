"""Integration tests for co-owner (OWNER-membership) management (UN-2202).

Exercises the shared owner-management surface — the ``owners/`` endpoints,
``AddOwnerSerializer`` / ``RemoveOwnerSerializer`` (incl. VIEWER->OWNER promotion
and the last-owner guard), the ``IsOwner`` permission class, ``for_user``
visibility, and ``HasMembersMixin`` — on Workflow, plus a parameterized sweep
across the OSS shareable resources.

DB-backed (Django ``TestCase``), so ``backend/conftest.py`` auto-marks these
``integration`` and the rig runs them in ``integration-backend``.
"""

from unittest.mock import Mock, patch

import pytest
from account_v2.models import User
from django.test import TestCase
from permissions.roles import ResourceRole
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.views import WorkflowViewSet

from permissions.membership_serializers import AddOwnerSerializer
from permissions.tests.base import (
    RESOURCE_SPECS,
    CoOwnerOrgTestMixin,
    make_user,
)


class WorkflowOwnerEndpointTests(CoOwnerOrgTestMixin, TestCase):
    """The ``owners/`` add/remove endpoints via the real WorkflowViewSet."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-1", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.factory = APIRequestFactory()

    def _add(self, actor: User, target_id: int) -> Response:
        view = WorkflowViewSet.as_view({"post": "add_co_owner"})
        request = self.factory.post("/x/", {"user_id": target_id}, format="json")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.workflow.pk))

    def _remove(self, actor: User, user_id: int) -> Response:
        view = WorkflowViewSet.as_view({"delete": "remove_co_owner"})
        request = self.factory.delete("/x/")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.workflow.pk), user_id=str(user_id))

    def _owner_ids(self) -> set[int]:
        return set(
            self.workflow.memberships.filter(role=ResourceRole.OWNER).values_list(
                "user_id", flat=True
            )
        )

    @pytest.mark.critical_path("co-owner-manage")
    def test_owner_adds_co_owner(self) -> None:
        response = self._add(self.owner, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.coowner.pk, self._owner_ids())
        self.assertIn(self.coowner.pk, [ref["id"] for ref in response.data["co_owners"]])

    def test_add_rejects_non_org_member(self) -> None:
        response = self._add(self.owner, self.stranger.pk)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_rejects_existing_owner(self) -> None:
        response = self._add(self.owner, self.owner.pk)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_add_promotes_viewer_to_owner(self) -> None:
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        response = self._add(self.owner, self.viewer.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(self.viewer.pk, self._owner_ids())
        # promotion, not duplication: exactly one row for the viewer
        self.assertEqual(self.workflow.memberships.filter(user=self.viewer).count(), 1)

    def test_viewer_cannot_add_co_owner(self) -> None:
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        response = self._add(self.viewer, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_outsider_gets_404(self) -> None:
        # for_user() filters the resource out before IsOwner runs → 404, not 403.
        response = self._add(self.outsider, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_add_co_owner(self) -> None:
        response = self._add(self.admin, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_owner_removes_co_owner(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        response = self._remove(self.owner, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertNotIn(self.coowner.pk, self._owner_ids())

    def test_remove_rejects_non_owner(self) -> None:
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        response = self._remove(self.owner, self.viewer.pk)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_remove_last_owner(self) -> None:
        response = self._remove(self.owner, self.owner.pk)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(self.owner.pk, self._owner_ids())

    def test_can_remove_when_multiple_owners(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        response = self._remove(self.owner, self.owner.pk)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._owner_ids(), {self.coowner.pk})


class OwnerModelAndPermissionTests(CoOwnerOrgTestMixin, TestCase):
    """IsOwner branches, for_user visibility, HasMembersMixin, save() org-derivation."""

    def setUp(self) -> None:
        self._seed_org()
        self.workflow = Workflow.objects.create(
            workflow_name="wf-1", organization=self.org, created_by=self.owner
        )
        self.workflow.memberships.create(user=self.owner, role=ResourceRole.OWNER)

    def test_is_owner_permission_branches(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        svc = make_user("svc@example.com", is_service_account=True)
        self.assertTrue(self._is_owner_perm(self.owner, self.workflow))
        self.assertTrue(self._is_owner_perm(self.coowner, self.workflow))
        self.assertTrue(self._is_owner_perm(self.admin, self.workflow))
        self.assertTrue(self._is_owner_perm(svc, self.workflow))
        self.assertFalse(self._is_owner_perm(self.viewer, self.workflow))
        self.assertFalse(self._is_owner_perm(self.outsider, self.workflow))

    def test_created_by_not_consulted_when_memberships_exist(self) -> None:
        # A creator with no OWNER row is not an owner — created_by is audit-only.
        orphan = Workflow.objects.create(
            workflow_name="wf-2", organization=self.org, created_by=self.outsider
        )
        self.assertFalse(self._is_owner_perm(self.outsider, orphan))

    def test_for_user_visibility_tracks_membership(self) -> None:
        self.assertNotIn(self.workflow, Workflow.objects.for_user(self.coowner))
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        self.assertIn(self.workflow, Workflow.objects.for_user(self.coowner))
        self.assertNotIn(self.workflow, Workflow.objects.for_user(self.outsider))

    def test_has_members_mixin_accessors(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        self.workflow.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.assertEqual(self.workflow.co_owners_count(), 2)
        self.assertTrue(self.workflow.is_owner(self.owner))
        self.assertTrue(self.workflow.is_owner(self.coowner))
        self.assertFalse(self.workflow.is_owner(self.viewer))
        self.assertEqual(
            {u.id for u in self.workflow.owners()}, {self.owner.pk, self.coowner.pk}
        )
        self.assertEqual({u.id for u in self.workflow.viewers()}, {self.viewer.pk})

    def test_membership_save_derives_organization(self) -> None:
        # organization is server-derived from the resource, never passed in.
        membership = self.workflow.memberships.create(
            user=self.viewer, role=ResourceRole.VIEWER
        )
        self.assertEqual(membership.organization_id, self.org.pk)


class CrossResourceOwnerManagementTests(CoOwnerOrgTestMixin, TestCase):
    """The shared owner-management surface behaves identically for every OSS
    shareable resource (AgenticProject is covered cloud-side)."""

    def setUp(self) -> None:
        self._seed_org()

    def test_add_owner_and_visibility_per_resource(self) -> None:
        for spec in RESOURCE_SPECS:
            with self.subTest(kind=spec.kind):
                resource = spec.build(self.org, self.owner)
                resource.memberships.create(user=self.owner, role=ResourceRole.OWNER)

                serializer = AddOwnerSerializer(
                    data={"user_id": self.coowner.pk}, context={"resource": resource}
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()

                owner_ids = set(
                    resource.memberships.filter(role=ResourceRole.OWNER).values_list(
                        "user_id", flat=True
                    )
                )
                self.assertEqual(owner_ids, {self.owner.pk, self.coowner.pk})
                self.assertTrue(resource.is_owner(self.coowner))

                manager = type(resource).objects
                self.assertIn(resource, manager.for_user(self.coowner))
                self.assertNotIn(resource, manager.for_user(self.outsider))
                self.assertTrue(self._is_owner_perm(self.coowner, resource))
                self.assertFalse(self._is_owner_perm(self.outsider, resource))


class OwnerNotificationWiringTests(CoOwnerOrgTestMixin, TestCase):
    """``add_co_owner`` / ``remove_co_owner`` fire the sharing-service
    notifications with the right payload, and swallow notification failures so
    the owners request is never broken (best-effort). The resource-type hook is
    patched to a fixed value so the test does not depend on the cloud-only
    notification plugin's conditional ``ResourceType`` import."""

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
            patch("permissions.membership_views.notification_plugin", plugin),
            patch.object(
                WorkflowViewSet,
                "get_notification_resource_type",
                return_value="workflow",
            ),
        ):
            p.start()
            self.addCleanup(p.stop)

    def _add(self, actor: User, target_id: int) -> Response:
        view = WorkflowViewSet.as_view({"post": "add_co_owner"})
        request = self.factory.post("/x/", {"user_id": target_id}, format="json")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.workflow.pk))

    def _remove(self, actor: User, user_id: int) -> Response:
        view = WorkflowViewSet.as_view({"delete": "remove_co_owner"})
        request = self.factory.delete("/x/")
        force_authenticate(request, user=actor)
        return view(request, pk=str(self.workflow.pk), user_id=str(user_id))

    def test_add_fires_added_notification_with_payload(self) -> None:
        response = self._add(self.owner, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.service.send_co_owner_added_notification.assert_called_once()
        kwargs = self.service.send_co_owner_added_notification.call_args.kwargs
        self.assertEqual(kwargs["resource_type"], "workflow")
        self.assertEqual(kwargs["resource_name"], "wf-1")
        self.assertEqual(kwargs["resource_id"], str(self.workflow.pk))
        self.assertEqual(kwargs["shared_by"], self.owner)
        self.assertEqual([u.pk for u in kwargs["shared_to"]], [self.coowner.pk])
        self.assertEqual(kwargs["resource_instance"], self.workflow)

    def test_remove_fires_removed_notification_with_payload(self) -> None:
        self.workflow.memberships.create(user=self.coowner, role=ResourceRole.OWNER)
        response = self._remove(self.owner, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.service.send_access_removed_notification.assert_called_once()
        kwargs = self.service.send_access_removed_notification.call_args.kwargs
        self.assertEqual(kwargs["resource_type"], "workflow")
        self.assertEqual([u.pk for u in kwargs["removed_from"]], [self.coowner.pk])
        self.assertEqual(kwargs["removed_by"], self.owner)
        self.assertEqual(kwargs["resource_id"], str(self.workflow.pk))
        self.assertEqual(kwargs["resource_instance"], self.workflow)

    def test_notification_failure_does_not_break_add(self) -> None:
        self.service.send_co_owner_added_notification.side_effect = RuntimeError("boom")
        response = self._add(self.owner, self.coowner.pk)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        owner_ids = set(
            self.workflow.memberships.filter(role=ResourceRole.OWNER).values_list(
                "user_id", flat=True
            )
        )
        self.assertIn(self.coowner.pk, owner_ids)
