"""Repair of ownerless ``CustomTool`` rows (UN-3057).

The Prompt Studio clone path created projects without the OWNER
``ResourceMembership`` that UN-2202 made authoritative, so every project cloned
after the UN-2202 backfill ran is ownerless: visible, but unmanageable by anyone
except an org admin. Fixing the clone helper stops new breakage; these already
broken rows need a repair pass.

Exercises the migration helper against the real models (``django.apps.apps``
satisfies the ``apps.get_model`` interface the migration passes in), so the
behaviour is pinned without driving the migration executor.
"""

from __future__ import annotations

import secrets

from account_v2.models import Organization, User
from django.apps import apps as django_apps
from django.test import TestCase
from permissions.roles import ResourceRole
from tenant_account_v2.migrations._membership_backfill import (
    repair_ownerless_owner_rows,
)

from prompt_studio.prompt_studio_core_v2.models import CustomTool

APP_LABEL = "prompt_studio_core_v2"
MODEL_NAME = "CustomTool"


def _make_user(email: str) -> User:
    return User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )


class RepairOwnerlessOwnerRowsTests(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        self.creator = _make_user("creator@example.com")
        self.other = _make_user("other@example.com")

    def _tool(self, name: str, creator: User | None) -> CustomTool:
        return CustomTool.objects.create(
            tool_name=name,
            description="",
            organization=self.org,
            created_by=creator,
        )

    def _repair(self) -> int:
        return repair_ownerless_owner_rows(django_apps, APP_LABEL, MODEL_NAME)

    def _owner_ids(self, tool: CustomTool) -> set:
        return set(
            tool.memberships.filter(role=ResourceRole.OWNER).values_list(
                "user_id", flat=True
            )
        )

    def test_ownerless_tool_gets_an_owner_row_for_its_creator(self) -> None:
        tool = self._tool("cloned-project", self.creator)
        self.assertEqual(self._owner_ids(tool), set())

        self._repair()

        self.assertEqual(self._owner_ids(tool), {self.creator.id})

    def test_tool_that_already_has_an_owner_is_left_alone(self) -> None:
        """A creator deliberately replaced by a co-owner must not be re-added."""
        tool = self._tool("handed-over-project", self.creator)
        tool.memberships.create(user=self.other, role=ResourceRole.OWNER)

        self._repair()

        self.assertEqual(self._owner_ids(tool), {self.other.id})

    def test_tool_with_no_creator_is_skipped(self) -> None:
        tool = self._tool("orphan-project", None)

        self._repair()

        self.assertEqual(self._owner_ids(tool), set())
