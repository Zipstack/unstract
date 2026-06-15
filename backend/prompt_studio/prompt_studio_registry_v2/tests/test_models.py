"""Exported-tool access follows the linked project's current share state,
not the export-time snapshot; unlinked (legacy) rows fall back to their own
share fields.

Covers ``PromptStudioRegistry.list_tools`` and its enforcement through
``ToolInstanceHelper.validate_tool_access``. Admin resolution is patched to a
deterministic predicate so the tests exercise share derivation, not the
active auth plugin's role handling.
"""

import secrets
from unittest.mock import patch

from account_v2.models import Organization, User
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from tenant_account_v2.models import OrganizationMember
from tool_instance_v2.tool_instance_helper import ToolInstanceHelper
from utils.user_context import UserContext

from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_registry_v2.models import PromptStudioRegistry


def _make_user(email: str) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


class RegistryShareDerivationTestBase(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        UserContext.set_organization_identifier(self.org.organization_id)

        self.owner = _make_user("owner@example.com")
        self.other = _make_user("other@example.com")
        self.admin = _make_user("admin@example.com")
        for user in (self.owner, self.other, self.admin):
            OrganizationMember.objects.create(
                organization=self.org, user=user, role="user"
            )

        patcher = patch(
            "tenant_account_v2.organization_member_service"
            ".OrganizationMemberService.is_user_organization_admin",
            side_effect=lambda user: getattr(user, "email", None) == self.admin.email,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.tool = CustomTool.objects.create(
            tool_name="contract-parser",
            description="Parses contracts",
            author=self.owner.email,
            created_by=self.owner,
            organization=self.org,
        )
        # Owner-only snapshot, as written by an unshared export.
        self.registry = PromptStudioRegistry.objects.create(
            name=self.tool.tool_name,
            custom_tool=self.tool,
            created_by=self.owner,
            organization=self.org,
        )
        self.registry.shared_users.add(self.owner)

    def _visible_ids(self, user: User) -> set:
        return set(
            PromptStudioRegistry.objects.list_tools(user).values_list(
                "prompt_registry_id", flat=True
            )
        )

    def _validate(self, user: User) -> None:
        ToolInstanceHelper.validate_tool_access(
            user=user, tool_uid=str(self.registry.prompt_registry_id)
        )


class ListToolsDerivationTests(RegistryShareDerivationTestBase):
    def test_owner_sees_own_tool(self) -> None:
        self.assertIn(self.registry.prompt_registry_id, self._visible_ids(self.owner))

    def test_unshared_tool_hidden_from_other_user(self) -> None:
        self.assertNotIn(self.registry.prompt_registry_id, self._visible_ids(self.other))

    def test_org_share_after_export_makes_tool_visible(self) -> None:
        self.tool.shared_to_org = True
        self.tool.save()
        self.assertIn(self.registry.prompt_registry_id, self._visible_ids(self.other))

    def test_user_share_after_export_makes_tool_visible(self) -> None:
        self.tool.shared_users.add(self.other)
        self.assertIn(self.registry.prompt_registry_id, self._visible_ids(self.other))

    def test_unshare_after_share_hides_tool(self) -> None:
        self.tool.shared_users.add(self.other)
        self.tool.shared_users.remove(self.other)
        self.assertNotIn(self.registry.prompt_registry_id, self._visible_ids(self.other))

    def test_legacy_row_falls_back_to_own_share_fields(self) -> None:
        shared = PromptStudioRegistry.objects.create(
            name="legacy-shared",
            custom_tool=None,
            created_by=self.owner,
            organization=self.org,
            shared_to_org=True,
        )
        private = PromptStudioRegistry.objects.create(
            name="legacy-private",
            custom_tool=None,
            created_by=self.owner,
            organization=self.org,
        )
        self.assertIn(shared.prompt_registry_id, self._visible_ids(self.other))
        self.assertNotIn(private.prompt_registry_id, self._visible_ids(self.other))

    def test_admin_sees_unshared_and_legacy_rows(self) -> None:
        legacy = PromptStudioRegistry.objects.create(
            name="legacy-tool",
            custom_tool=None,
            created_by=self.owner,
            organization=self.org,
        )
        visible = self._visible_ids(self.admin)
        self.assertIn(self.registry.prompt_registry_id, visible)
        self.assertIn(legacy.prompt_registry_id, visible)


class ValidateToolAccessTests(RegistryShareDerivationTestBase):
    def test_owner_allowed(self) -> None:
        self._validate(self.owner)

    def test_unshared_user_denied(self) -> None:
        with self.assertRaises(PermissionDenied):
            self._validate(self.other)

    def test_share_after_export_allows_user(self) -> None:
        self.tool.shared_to_org = True
        self.tool.save()
        self._validate(self.other)

    def test_registry_snapshot_alone_does_not_grant_access(self) -> None:
        # The project's share state wins over the registry snapshot.
        self.registry.shared_users.add(self.other)
        with self.assertRaises(PermissionDenied):
            self._validate(self.other)
