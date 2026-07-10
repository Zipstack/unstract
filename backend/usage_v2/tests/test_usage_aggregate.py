"""Critical path ``usage-aggregate-read``: per-run token usage aggregates
correctly and never crosses organization boundaries.

Usage rows are written by workers, but the aggregation that bills against them
is a synchronous read. Under-counting loses revenue; leaking another org's rows
into the sum is both a billing and a disclosure bug — the org scoping lives in a
default manager, so a stray ``objects`` -> ``_base_manager`` change would break
it silently. Needs a live DB (integration tier).
"""

from __future__ import annotations

import secrets
import uuid

import pytest
from account_v2.models import Organization, User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from usage_v2.models import Usage, UsageType


def _usage(organization: Organization, run_id: uuid.UUID, tokens: int) -> Usage:
    return Usage.objects.create(
        organization=organization,
        run_id=run_id,
        adapter_instance_id=str(uuid.uuid4()),
        usage_type=UsageType.LLM,
        model_name="gpt-4o-mini",
        embedding_tokens=0,
        prompt_tokens=tokens,
        completion_tokens=tokens,
        total_tokens=tokens * 2,
        cost_in_dollars=0.5,
    )


class UsageAggregateReadTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-usage", display_name="Org Usage", organization_id="org-usage"
        )
        self.other_org = Organization.objects.create(
            name="org-other", display_name="Org Other", organization_id="org-other"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.user = User.objects.create_user(
            username="biller@example.com",
            email="biller@example.com",
            password=secrets.token_urlsafe(),
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )
        self.run_id = uuid.uuid4()
        self.factory = APIRequestFactory()

    @pytest.mark.critical_path("usage-aggregate-read")
    def test_token_usage_sums_own_org_only(self) -> None:
        _usage(self.org, self.run_id, tokens=100)
        _usage(self.org, self.run_id, tokens=50)
        _usage(self.org, uuid.uuid4(), tokens=999)  # different run
        _usage(self.other_org, self.run_id, tokens=777)  # same run, other org

        # Deferred: UsageView's filterset resolves a queryset at class-body
        # evaluation, so a module-scope import queries the DB during pytest
        # collection — before any test has DB access.
        from usage_v2.views import UsageView

        view = UsageView.as_view({"get": "get_token_usage"})
        request = self.factory.get(
            "/api/v1/usage/get_token_usage/", {"run_id": self.run_id}
        )
        force_authenticate(request, user=self.user)
        response = view(request)

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["prompt_tokens"] == 150
        assert response.data["completion_tokens"] == 150
        assert response.data["total_tokens"] == 300
        assert response.data["cost_in_dollars"] == pytest.approx(1.0)
