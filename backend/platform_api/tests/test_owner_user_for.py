"""The `owner_user_for` resolver in isolation.

End-to-end coverage of the create sites that call it lives in
`test_platform_key_resource_ownership.py`.
"""

import secrets
import uuid

from account_v2.models import Organization, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from platform_api.models import ApiKeyPermission, PlatformApiKey
from platform_api.services import create_api_user_for_key, owner_user_for
from rest_framework.test import APITestCase

ORG = "org-owner-test"


def _make_user() -> User:
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


class OwnerUserForTest(APITestCase):
    """The resolver in isolation."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG, display_name="Owner Test", organization_id=ORG
        )

    def _make_key(self, created_by: User | None) -> PlatformApiKey:
        key = PlatformApiKey.objects.create(
            name=f"key-{uuid.uuid4().hex[:8]}",
            description="test key",
            organization=self.org,
            permission=ApiKeyPermission.FULL_ACCESS,
            created_by=created_by,
        )
        # The minting path, for the `is_service_account` flag it sets.
        create_api_user_for_key(key, self.org)
        key.refresh_from_db()
        return key

    def test_a_normal_user_is_returned_unchanged(self) -> None:
        user = _make_user()
        self.assertEqual(owner_user_for(user), user)

    def test_a_normal_user_costs_no_query(self) -> None:
        """The early return is the hot path — every create site calls this."""
        user = _make_user()
        with CaptureQueriesContext(connection) as queries:
            owner_user_for(user)
        self.assertEqual(len(queries), 0)

    def test_a_service_account_resolves_to_the_keys_creator(self) -> None:
        creator = _make_user()
        key = self._make_key(created_by=creator)
        self.assertEqual(owner_user_for(key.api_user), creator)

    def test_a_deleted_creator_leaves_the_resource_ownerless(self) -> None:
        """`created_by` is SET_NULL, so the key can outlive its creator."""
        key = self._make_key(created_by=_make_user())
        PlatformApiKey.objects.filter(pk=key.pk).update(created_by=None)
        self.assertEqual(owner_user_for(key.api_user), key.api_user)

    def test_a_service_account_with_no_key_stays_itself(self) -> None:
        key = self._make_key(created_by=_make_user())
        service_account = key.api_user
        PlatformApiKey.objects.filter(pk=key.pk).delete()
        self.assertEqual(owner_user_for(service_account), service_account)
