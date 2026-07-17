"""Critical path ``prompt-studio-author``: create a Prompt Studio project and
add a prompt to it.

Authoring is the synchronous half of prompt-studio-fetch-response — running a
prompt needs a real LLM, but composing one does not. A project must be creatable
before any adapter is configured (a fresh org has none), and prompts must bind
to their project. Needs a live DB (integration tier).
"""

from __future__ import annotations

import secrets

import pytest
from account_v2.models import Organization, User
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import OrganizationMember
from utils.user_context import UserContext

from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt


class PromptStudioAuthorAPITest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name="org-ps", display_name="Org PS", organization_id="org-ps"
        )
        UserContext.set_organization_identifier(self.org.organization_id)
        self.user = User.objects.create_user(
            username="prompter@example.com",
            email="prompter@example.com",
            password=secrets.token_urlsafe(),
        )
        OrganizationMember.objects.create(
            organization=self.org, user=self.user, role="user"
        )
        self.factory = APIRequestFactory()

    def _call(self, view, method: str, path: str, payload: dict, **kwargs):
        request = getattr(self.factory, method)(path, payload, format="json")
        force_authenticate(request, user=self.user)
        return view(request, **kwargs)

    @pytest.mark.critical_path("prompt-studio-author")
    def test_create_project_then_add_prompt(self) -> None:
        create_project = PromptStudioCoreView.as_view({"post": "create"})
        project = self._call(
            create_project,
            "post",
            "/api/v1/prompt-studio/",
            {
                "tool_name": "invoice-parser",
                "description": "extracts invoice fields",
                "author": "test",
            },
        )
        assert project.status_code == status.HTTP_201_CREATED, project.data

        tool = CustomTool.objects.get(tool_id=project.data["tool_id"])
        assert tool.organization_id == self.org.id
        assert tool.created_by == self.user

        create_prompt = PromptStudioCoreView.as_view({"post": "create_prompt"})
        prompt = self._call(
            create_prompt,
            "post",
            f"/api/v1/prompt-studio/prompt-studio-prompt/{tool.tool_id}/",
            {
                "tool_id": str(tool.tool_id),
                "prompt_key": "invoice_number",
                "prompt": "What is the invoice number?",
                "prompt_type": ToolStudioPrompt.PromptType.PROMPT,
                "sequence_number": 1,
            },
            pk=str(tool.tool_id),
        )
        assert prompt.status_code == status.HTTP_201_CREATED, prompt.data

        persisted = ToolStudioPrompt.objects.get(prompt_id=prompt.data["prompt_id"])
        assert persisted.tool_id_id == tool.tool_id
        assert persisted.active

    def test_list_modified_at_reflects_prompt_edits(self) -> None:
        """Prompt edits don't touch the CustomTool row; the list endpoint must
        surface the latest prompt modified_at instead (UN-3741).
        """
        # Create via the API so ownership membership rows (UN-2202) exist —
        # a bare objects.create() is invisible to the list queryset
        create_project = PromptStudioCoreView.as_view({"post": "create"})
        project = self._call(
            create_project,
            "post",
            "/api/v1/prompt-studio/",
            {
                "tool_name": "quote-parser",
                "description": "extracts quote fields",
                "author": "test",
            },
        )
        assert project.status_code == status.HTTP_201_CREATED, project.data
        tool = CustomTool.objects.get(tool_id=project.data["tool_id"])
        prompt = ToolStudioPrompt.objects.create(
            tool_id=tool,
            prompt_key="quote_number",
            prompt="What is the quote number?",
            prompt_type=ToolStudioPrompt.PromptType.PROMPT,
            sequence_number=1,
        )
        assert prompt.modified_at > tool.modified_at

        list_view = PromptStudioCoreView.as_view({"get": "list"})
        response = self._call(list_view, "get", "/api/v1/prompt-studio/", {})
        assert response.status_code == status.HTTP_200_OK, response.data

        rows = response.data
        if isinstance(rows, dict):  # paginated response
            rows = rows["results"]
        row = next(r for r in rows if str(r["tool_id"]) == str(tool.tool_id))
        assert row["modified_at"] == prompt.modified_at
        assert row["created_at"] is not None
