"""View-level tests for the group-notification internal endpoints.

The send-side logic (who gets mailed, the tri-state plugin contract) is
covered in ``ResourceShareNotificationTests`` in ``tests.py``. These pin the
one thing that lives only here: the status-code mapping from that result to
an HTTP response, since that mapping is what the worker's retry decision
actually reads. ``send_resource_shared`` / ``send_membership_changed`` are
patched directly so these don't need a full group/resource DB setup to
exercise the view in isolation.
"""

from unittest.mock import patch

from account_v2.models import Organization
from django.test import RequestFactory, TestCase
from rest_framework import status
from utils.user_context import UserContext

from tenant_account_v2.internal_views import (
    GroupMembershipChangedView,
    ResourceSharedWithGroupView,
)

_SHARE_PAYLOAD = {
    "group_ids": [1],
    "actor_id": 1,
    "resource_kind": "workflow",
    "resource_id": "wf-1",
    "share_action": "shared",
    "revoked_at": None,
}

_MEMBERSHIP_PAYLOAD = {
    "group_id": 1,
    "actor_id": 1,
    "membership_action": "added",
    "user_ids": [1],
}


class _InternalViewTestBase(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-views", display_name="Org Views", organization_id="org-views"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.addCleanup(UserContext.set_organization_identifier, None)

    @staticmethod
    def _post(view_cls, data: dict):
        request = RequestFactory().post(
            "/internal/", data=data, content_type="application/json"
        )
        return view_cls.as_view()(request)


class ResourceSharedWithGroupViewTests(_InternalViewTestBase):
    def test_sent_returns_200(self) -> None:
        with patch(
            "tenant_account_v2.internal_views.send_resource_shared", return_value=True
        ):
            response = self._post(ResourceSharedWithGroupView, _SHARE_PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "success")

    def test_genuine_failure_returns_502(self) -> None:
        # This is the branch the Critical hinged on: before the tri-state
        # fix, every skip (unconfigured template, disabled notifications,
        # bad input) collapsed into this same False -- retrying forever a
        # condition no retry could fix.
        with patch(
            "tenant_account_v2.internal_views.send_resource_shared", return_value=False
        ):
            response = self._post(ResourceSharedWithGroupView, _SHARE_PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["status"], "failed")


class GroupMembershipChangedViewTests(_InternalViewTestBase):
    def test_sent_returns_200(self) -> None:
        with patch(
            "tenant_account_v2.internal_views.send_membership_changed", return_value=True
        ):
            response = self._post(GroupMembershipChangedView, _MEMBERSHIP_PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_genuine_failure_returns_502(self) -> None:
        with patch(
            "tenant_account_v2.internal_views.send_membership_changed",
            return_value=False,
        ):
            response = self._post(GroupMembershipChangedView, _MEMBERSHIP_PAYLOAD)
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
