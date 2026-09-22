"""UN-3487: `file/`, `file/download` and `file/upload` are scoped to the
caller, not just the org.

Before this fix, `FileManagementViewSet` resolved a connector by a raw
`ConnectorInstance.objects.get(pk=id)` — any authenticated org member who
knew (or guessed) another user's connector id could browse, download from,
or upload to it, sharing settings aside. These drive the real views through
DRF's request factory, so a gate that exists only in the queryset — and
never reaches the route — is still caught.
"""

from unittest.mock import patch

from connector_v2.models import ConnectorInstance
from django.test import TestCase
from permissions.roles import ResourceRole
from permissions.tests.base import CoOwnerOrgTestMixin
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate

from file_management.views import FileManagementViewSet


class FileManagementAccessScopeTest(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()
        self.connector = ConnectorInstance.objects.create(
            connector_name="team-a-s3",
            connector_id="minio|c799f6e3-2b57-434e-aaac-b5daa415da19",
            connector_metadata={"bucket": "team-a-data"},
            organization=self.org,
            created_by=self.owner,
        )
        # `created_by` is audit-only — access runs through the membership
        # table, same as every other shareable resource in this codebase.
        self.connector.memberships.create(user=self.owner, role=ResourceRole.OWNER)
        self.connector.memberships.create(user=self.viewer, role=ResourceRole.VIEWER)
        self.factory = APIRequestFactory()

    def _list(self, actor) -> Response:
        view = FileManagementViewSet.as_view({"get": "list"})
        request = self.factory.get(
            "/file", {"connector_id": str(self.connector.pk), "path": "/"}
        )
        force_authenticate(request, user=actor)
        with (
            patch(
                "file_management.views.FileManagerHelper.get_file_system",
                return_value=None,
            ),
            patch("file_management.views.FileManagerHelper.list_files", return_value=[]),
        ):
            return view(request)

    def test_owner_can_list_their_own_connector(self) -> None:
        self.assertEqual(self._list(self.owner).status_code, status.HTTP_200_OK)

    def test_org_admin_can_list_any_connector(self) -> None:
        self.assertEqual(self._list(self.admin).status_code, status.HTTP_200_OK)

    def test_shared_viewer_can_list_the_connector(self) -> None:
        self.assertEqual(self._list(self.viewer).status_code, status.HTTP_200_OK)

    def test_outsider_org_member_cannot_list_an_unshared_connector(self) -> None:
        # In scope (org member), but the connector was never shared with them.
        self.assertEqual(self._list(self.outsider).status_code, status.HTTP_404_NOT_FOUND)

    def test_non_org_member_cannot_list_the_connector(self) -> None:
        self.assertEqual(self._list(self.stranger).status_code, status.HTTP_404_NOT_FOUND)
