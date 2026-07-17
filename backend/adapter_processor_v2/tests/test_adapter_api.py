"""Critical path ``adapter-register-llm``: POST /api/v1/adapter/ registers an
LLM adapter. Exercises the real endpoint wiring — auth, serializer, metadata
encryption, org-scoped persistence — with only the SDK context-window lookup
(a provider-shaped call) mocked. Needs a live DB (integration tier).
"""

from __future__ import annotations

import secrets
from datetime import timedelta
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

    @patch.object(AdapterInstance, "get_context_window_size", return_value=4096)
    def test_list_serves_timestamps_and_rename_bumps_modified(self, _ctx) -> None:
        """UN-3741: the list endpoint must serve created_at/modified_at, and a
        rename must advance modified_at while created_at stays stable — the
        Meta.fields tuple is hand-maintained, so this pins the two lines.
        """
        payload = {
            "adapter_id": "openai|test-llm",
            "adapter_name": "list-me",
            "adapter_type": "LLM",
            "adapter_metadata": {"api_key": "sk-test", "model": "gpt-4o-mini"},
        }
        request = APIRequestFactory().post("/api/v1/adapter/", payload, format="json")
        force_authenticate(request, user=self.user)
        created = self.create_view(request)
        assert created.status_code == status.HTTP_201_CREATED, created.data
        adapter_id = created.data["id"]

        list_view = AdapterInstanceViewSet.as_view({"get": "list"})

        def _list_row():
            request = APIRequestFactory().get("/api/v1/adapter/")
            force_authenticate(request, user=self.user)
            response = list_view(request)
            assert response.status_code == status.HTTP_200_OK, response.data
            rows = response.data
            if isinstance(rows, dict):  # paginated response
                rows = rows["results"]
            return next(r for r in rows if str(r["id"]) == str(adapter_id))

        row = _list_row()
        assert row["created_at"] is not None
        assert row["modified_at"] is not None
        created_at_before = row["created_at"]

        # Backdate so the rename's auto_now bump is strictly observable
        instance = AdapterInstance.objects.get(pk=adapter_id)
        AdapterInstance.objects.filter(pk=adapter_id).update(
            modified_at=instance.modified_at - timedelta(hours=1)
        )
        modified_at_before = _list_row()["modified_at"]

        update_view = AdapterInstanceViewSet.as_view({"patch": "partial_update"})
        request = APIRequestFactory().patch(
            f"/api/v1/adapter/{adapter_id}/",
            {"adapter_name": "renamed-adapter"},
            format="json",
        )
        force_authenticate(request, user=self.user)
        updated = update_view(request, pk=adapter_id)
        assert updated.status_code == status.HTTP_200_OK, updated.data

        row = _list_row()
        assert row["modified_at"] > modified_at_before, "rename must bump"
        assert row["created_at"] == created_at_before, "created_at is stable"
