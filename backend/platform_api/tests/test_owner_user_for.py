"""The ownership resolvers in isolation.

End-to-end coverage of the create sites that call them lives in
`test_platform_key_resource_ownership.py`.
"""

import secrets
import uuid
from types import SimpleNamespace

from account_v2.enums import UserRole
from account_v2.models import Organization, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from permissions.roles import ResourceRole
from platform_api.models import ApiKeyPermission, PlatformApiKey
from platform_api.services import create_api_user_for_key, owner_user_for
from rest_framework.test import APIRequestFactory, APITestCase
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

ORG = "org-owner-test"


def _make_user() -> User:
    email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


class _KeyFixture:
    """Org, a member who mints keys, and the minting path itself."""

    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG, display_name="Owner Test", organization_id=ORG
        )

    def _make_member(self) -> User:
        """A key creator as production guarantees one.

        ``IsOrganizationAdmin`` resolves the caller's ``OrganizationMember``
        before allowing key creation, so a key's ``created_by`` is always a
        member of that org at mint time.
        """
        user = _make_user()
        OrganizationMember.objects.create(
            user=user, organization=self.org, role=UserRole.ADMIN.value
        )
        return user

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


class OwnerUserForTest(_KeyFixture, APITestCase):
    """The resolver in isolation."""

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
        creator = self._make_member()
        key = self._make_key(created_by=creator)
        self.assertEqual(owner_user_for(key.api_user), creator)

    def test_a_deleted_creator_leaves_the_resource_ownerless(self) -> None:
        """`created_by` is SET_NULL, so the key can outlive its creator."""
        key = self._make_key(created_by=self._make_member())
        PlatformApiKey.objects.filter(pk=key.pk).update(created_by=None)
        self.assertEqual(owner_user_for(key.api_user), key.api_user)

    def test_a_service_account_with_no_key_stays_itself(self) -> None:
        key = self._make_key(created_by=self._make_member())
        service_account = key.api_user
        PlatformApiKey.objects.filter(pk=key.pk).delete()
        self.assertEqual(owner_user_for(service_account), service_account)

    def test_a_creator_who_left_the_org_leaves_the_resource_ownerless(self) -> None:
        """An ex-member must not be granted OWNER; it would survive re-invite."""
        creator = self._make_member()
        key = self._make_key(created_by=creator)
        # _base_manager: the default one is org-scoped and UserContext is unset.
        OrganizationMember._base_manager.filter(
            user=creator, organization=self.org
        ).delete()
        self.assertEqual(owner_user_for(key.api_user), key.api_user)

    def test_a_creator_in_a_different_org_is_not_granted(self) -> None:
        """Membership is checked against the key's org, not any org."""
        creator = _make_user()
        other_org = Organization.objects.create(
            name="other", display_name="Other", organization_id="org-other"
        )
        OrganizationMember.objects.create(
            user=creator, organization=other_org, role=UserRole.ADMIN.value
        )
        key = self._make_key(created_by=creator)
        self.assertEqual(owner_user_for(key.api_user), key.api_user)


class KeyDeletionSuccessorTest(_KeyFixture, APITestCase):
    """Deleting a key must not hand its rows to a departed creator."""

    def _owner_row_users(self, resource):
        return {m.user_id for m in resource.memberships.filter(role=ResourceRole.OWNER)}

    def _key_owned_workflow(self, creator):
        from workflow_manager.workflow_v2.models.workflow import Workflow

        key = self._make_key(created_by=creator)
        workflow = Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:8]}", organization=self.org
        )
        workflow.memberships.create(
            user=key.api_user, role=ResourceRole.OWNER, organization=self.org
        )
        return key, workflow

    def test_a_live_creator_inherits_the_rows(self) -> None:
        creator = self._make_member()
        key, workflow = self._key_owned_workflow(creator)
        key.delete()
        self.assertEqual(self._owner_row_users(workflow), {creator.id})

    def test_a_departed_creator_inherits_nothing(self) -> None:
        creator = self._make_member()
        key, workflow = self._key_owned_workflow(creator)
        OrganizationMember._base_manager.filter(
            user=creator, organization=self.org
        ).delete()
        key.delete()
        self.assertNotIn(creator.id, self._owner_row_users(workflow))

    def test_a_departed_creator_still_keeps_the_audit_trail(self) -> None:
        """Deleting the account is SET_NULL on created_by; a null breaks deletes."""
        creator = self._make_member()
        key, workflow = self._key_owned_workflow(creator)
        workflow.created_by = key.api_user
        workflow.save(update_fields=["created_by"])
        OrganizationMember._base_manager.filter(
            user=creator, organization=self.org
        ).delete()

        key.delete()

        workflow.refresh_from_db()
        self.assertEqual(workflow.created_by_id, creator.id)


class ServiceAccountStaysAuthorizedTest(_KeyFixture, APITestCase):
    """Ownership no longer names the service account, so the gates that read
    ownership need their own bypass -- otherwise a key cannot use what it made.
    """

    def test_adapter_access_admits_a_service_account(self) -> None:
        from adapter_processor_v2.models import AdapterInstance
        from tool_instance_v2.tool_instance_helper import ToolInstanceHelper

        creator = self._make_member()
        key = self._make_key(created_by=creator)
        adapter = AdapterInstance.objects.create(
            adapter_name=f"a-{uuid.uuid4().hex[:8]}",
            adapter_id=f"llm|{uuid.uuid4()}",
            adapter_type="LLM",
            adapter_metadata={},
            organization=self.org,
            created_by=creator,
        )
        adapter.grant_owner(creator)
        # AdapterInstance.objects is org-scoped; without this the gate sees an
        # empty queryset and the assertion proves nothing.
        UserContext.set_organization_identifier(ORG)
        self.addCleanup(UserContext.set_organization_identifier, None)

        # Raises PermissionDenied without the bypass.
        ToolInstanceHelper.validate_adapter_access(
            user=key.api_user, adapter_ids={str(adapter.id)}
        )

    def test_adapter_delete_admits_a_service_account(self) -> None:
        """A key must be able to delete the adapter it created."""
        from adapter_processor_v2.models import AdapterInstance
        from permissions.permission import IsFrictionLessAdapterDelete

        creator = self._make_member()
        key = self._make_key(created_by=creator)
        adapter = AdapterInstance.objects.create(
            adapter_name=f"a-{uuid.uuid4().hex[:8]}",
            adapter_id=f"llm|{uuid.uuid4()}",
            adapter_type="LLM",
            adapter_metadata={},
            organization=self.org,
            created_by=creator,
        )
        adapter.grant_owner(creator)

        request = APIRequestFactory().delete("/")
        request.user = key.api_user

        self.assertTrue(
            IsFrictionLessAdapterDelete().has_object_permission(
                request, view=None, obj=adapter
            )
        )

    def test_workflow_permission_admits_a_service_account(self) -> None:
        from workflow_manager.workflow_v2.models.workflow import Workflow
        from workflow_manager.workflow_v2.permissions import IsWorkflowOwnerOrShared

        creator = self._make_member()
        key = self._make_key(created_by=creator)
        workflow = Workflow.objects.create(
            workflow_name=f"wf-{uuid.uuid4().hex[:8]}", organization=self.org
        )
        workflow.grant_owner(creator)

        request = APIRequestFactory().get("/")
        request.user = key.api_user
        view = SimpleNamespace(kwargs={"workflow_id": str(workflow.id)})
        # The permission resolves the workflow through the org-scoped manager.
        UserContext.set_organization_identifier(ORG)
        self.addCleanup(UserContext.set_organization_identifier, None)

        self.assertTrue(IsWorkflowOwnerOrShared().has_permission(request, view))
