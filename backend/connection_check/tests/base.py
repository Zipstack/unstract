"""Shared fixtures: an org with an owner and a member, a second org, saved
profiles, and a helper that calls a viewset action like a request would.
"""

import secrets
from typing import Any
from unittest.mock import MagicMock, patch

from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from connector_v2.models import ConnectorInstance
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.tests.auth_seam import member_role
from utils.user_context import UserContext

from connection_check.constants import ConnectionStatus
from connection_check.models import ConnectionTestResult, Profile
from unstract.connectors.connectorkit import Connectorkit

OPENAI_LLM_ID = "openai|502ecf49-e47c-445c-9907-6d4b90c5cd17"
MINIO_CONNECTOR_ID = "minio|c799f6e3-2b57-434e-aaac-b5daa415da19"
NEW_KEYS = [
    "last_test_status",
    "last_tested_at",
    "last_failure_reason",
    "tested_before_last_change",
]


def mock_llm(result: Any = True, error: Exception | None = None) -> Any:
    """Patch the SDK LLM that ``AdapterProcessor.test_adapter`` builds."""
    llm = MagicMock()
    llm.return_value.test_connection.return_value = result
    llm.return_value.test_connection.side_effect = error
    return patch("adapter_processor_v2.adapter_processor.LLM", llm)


def mock_connector_kit(result: Any = True, error: Exception | None = None) -> Any:
    """Patch the connector that ``ConnectorProcessor.test_connectors`` builds."""
    connector = MagicMock()
    connector.test_credentials.return_value = result
    connector.test_credentials.side_effect = error
    # Connectorkit is a singleton, so patch its one instance.
    return patch.object(Connectorkit(), "get_connector_by_id", return_value=connector)


def make_user(email: str) -> User:
    user: User = User.objects.create_user(
        username=email, email=email, password=secrets.token_urlsafe()
    )
    return user


class ConnectionCheckTestBase(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        self.other_org = Organization.objects.create(
            name="org-b", display_name="Org B", organization_id="org-b"
        )
        self.use_org(self.org)
        self.owner = make_user("owner@example.com")
        self.member = make_user("member@example.com")
        for user in (self.owner, self.member):
            OrganizationMember.objects.create(
                organization=self.org, user=user, role=member_role()
            )
        self.factory = APIRequestFactory()

    def use_org(self, organization: Organization) -> None:
        UserContext.set_organization_identifier(organization.organization_id)

    def call(
        self,
        viewset: Any,
        method: str,
        action: str,
        user: User | None = None,
        path: str = "/",
        data: Any = None,
        **url_kwargs: Any,
    ) -> Any:
        view = viewset.as_view({method: action})
        request = getattr(self.factory, method)(path, data, format="json")
        force_authenticate(request, user=user or self.owner)
        return view(request, **url_kwargs)

    def make_adapter(self, name: str, **fields: Any) -> AdapterInstance:
        adapter = AdapterInstance(
            adapter_name=name,
            adapter_id=OPENAI_LLM_ID,
            adapter_type="LLM",
            adapter_metadata={"api_key": "sk-test", "model": "gpt-4o-mini"},
            organization=self.org,
            created_by=self.owner,
            **fields,
        )
        adapter.create_adapter()
        adapter.grant_owner(self.owner)
        return adapter

    def make_connector(self, name: str, **fields: Any) -> ConnectorInstance:
        connector: ConnectorInstance = ConnectorInstance.objects.create(
            connector_name=name,
            connector_id=MINIO_CONNECTOR_ID,
            connector_metadata={"key": "k", "secret": "s", "bucket": "b"},
            organization=self.org,
            created_by=self.owner,
            **fields,
        )
        connector.grant_owner(self.owner)
        return connector

    def store_result(
        self,
        result_model: type[ConnectionTestResult],
        profile: Profile,
        status: str,
        reason: str | None = None,
    ) -> ConnectionTestResult:
        result: ConnectionTestResult = result_model.objects.create(
            profile=profile,
            organization=profile.organization,
            status=status,
            tested_at=timezone.now(),
            failure_reason=reason if status == ConnectionStatus.FAILED else None,
        )
        return result

    @staticmethod
    def rows(response: Any) -> list[dict[str, Any]]:
        data = response.data
        rows: list[dict[str, Any]] = (
            data["results"] if isinstance(data, dict) else data
        )
        return rows
