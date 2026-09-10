"""``set_default_triad`` must not re-validate defaults the user did not change.

The Default Triad UI submits all four defaults on every save, so a user whose
stored default was deprecated underneath them would otherwise be locked out of
changing any of the other three. Needs a live DB (integration tier).
"""

from __future__ import annotations

import secrets

import pytest
from account_v2.models import Organization, User
from django.test import TestCase
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from adapter_processor_v2.adapter_processor import AdapterProcessor
from adapter_processor_v2.exceptions import DeprecatedAdapter
from adapter_processor_v2.models import AdapterInstance, UserDefaultAdapter

LLM_WHISPERER_V1 = "llmwhisperer|0a1647f0-f65f-410d-843b-3d979c78350e"


class SetDefaultTriadDeprecationTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-triad", display_name="Org Triad", organization_id="org-triad"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.user = User.objects.create_user(
            username="triad@example.com",
            email="triad@example.com",
            password=secrets.token_urlsafe(),
        )
        self.member = OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )

        def make(adapter_id: str, name: str, adapter_type: str, available=True):
            return AdapterInstance.objects.create(
                adapter_id=adapter_id,
                adapter_name=name,
                adapter_type=adapter_type,
                organization=self.org,
                created_by=self.user,
                is_available=available,
            )

        self.llm_a = make("openai|llm-a", "llm-a", "LLM")
        self.llm_b = make("openai|llm-b", "llm-b", "LLM")
        # The user's stored X2TEXT default, deprecated out from under them by
        # migration 0007.
        self.stale_x2text = make(LLM_WHISPERER_V1, "old-whisperer", "X2TEXT", False)

        UserDefaultAdapter.objects.create(
            organization_member=self.member,
            default_llm_adapter=self.llm_a,
            default_x2text_adapter=self.stale_x2text,
        )

    def test_changing_one_default_tolerates_a_stale_deprecated_default(self) -> None:
        """The regression: resubmitting the unchanged deprecated id must pass."""
        AdapterProcessor.set_default_triad(
            {
                "llm_default": str(self.llm_b.id),
                "x2text_default": str(self.stale_x2text.id),
            },
            self.user,
        )

        defaults = UserDefaultAdapter.objects.get(organization_member=self.member)
        assert defaults.default_llm_adapter_id == self.llm_b.id
        # untouched, still pointing at the deprecated adapter
        assert defaults.default_x2text_adapter_id == self.stale_x2text.id

    def test_newly_selecting_a_deprecated_adapter_is_still_rejected(self) -> None:
        """Skipping unchanged values must not weaken the guard itself."""
        other = AdapterInstance.objects.create(
            adapter_id=LLM_WHISPERER_V1,
            adapter_name="another-whisperer",
            adapter_type="X2TEXT",
            organization=self.org,
            created_by=self.user,
            is_available=False,
        )

        with pytest.raises(DeprecatedAdapter):
            AdapterProcessor.set_default_triad(
                {"x2text_default": str(other.id)}, self.user
            )
