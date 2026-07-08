"""Critical path ``adapter-register-llm``: POST /api/v1/adapter/ registers an
LLM adapter. Exercises the real endpoint wiring — auth, serializer, metadata
encryption, org-scoped persistence — with only the SDK context-window lookup
(a provider-shaped call) mocked. Needs a live DB (integration tier).
"""

from __future__ import annotations

import secrets
from unittest.mock import patch

import pytest
from account_v2.models import Organization, User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from adapter_processor_v2.models import AdapterInstance
from adapter_processor_v2.views import AdapterInstanceViewSet


class AdapterRegisterLLMAPITest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-a", display_name="Org A", organization_id="org-a"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.user = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password=secrets.token_urlsafe(),
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )
        self.create_view = AdapterInstanceViewSet.as_view({"post": "create"})

    @pytest.mark.critical_path("adapter-register-llm")
    @patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
    def test_register_llm_adapter_persists_encrypted(self, _ctx_window) -> None:
        payload = {
            "adapter_id": "openai|test-llm",
            "adapter_name": "my-openai",
            "adapter_type": "LLM",
            "adapter_metadata": {"api_key": "sk-test", "model": "gpt-4o-mini"},
        }
        request = APIRequestFactory().post("/api/v1/adapter/", payload, format="json")
        force_authenticate(request, user=self.user)

        response = self.create_view(request)

        assert response.status_code == status.HTTP_201_CREATED, response.data
        instance = AdapterInstance.objects.get(adapter_name="my-openai")
        # persisted under the request user's org, created_by the request user
        assert instance.organization_id == self.org.id
        assert instance.created_by == self.user
        # metadata stored encrypted (binary), decrypts back via .metadata
        assert instance.adapter_metadata_b is not None
        assert instance.metadata["model"] == "gpt-4o-mini"
