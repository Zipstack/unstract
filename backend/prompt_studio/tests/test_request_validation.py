"""The 400/500 guards on the prompt-studio output and callback handlers.

Each of these replaces a 500: a non-UUID id raises Django's ``ValidationError``
while the query is being *built*, which drf_standardized_errors does not map;
a missing organization compiles to ``IS NULL`` and serves a blank project that
has real outputs; and a failed extraction-status write reports success.

Every case here was checked against the unguarded code first — strip the guard
and the case fails.
"""

import json
import secrets
import uuid
from unittest.mock import patch

from account_v2.models import Organization, User
from django.test import TestCase
from prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper import (
    ExtractionStatusResult,
)
from prompt_studio.prompt_studio_output_manager_v2.views import PromptStudioOutputView
from rest_framework.test import APIRequestFactory, force_authenticate
from utils.user_context import UserContext

_LIST = PromptStudioOutputView.as_view({"get": "list"})
_DEFAULT_PROFILE = PromptStudioOutputView.as_view({"get": "get_output_for_tool_default"})
_LATEST_BY_KEYS = PromptStudioOutputView.as_view({"get": "latest_outputs_by_keys"})


class OutputViewValidationTest(TestCase):
    def setUp(self):
        self.addCleanup(UserContext.set_organization_identifier, None)
        slug = f"val-{secrets.token_hex(3)}"
        self.org = Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )
        UserContext.set_organization_identifier(slug)
        self.user = User.objects.create_user(
            username=f"{slug}@example.com",
            email=f"{slug}@example.com",
            password=secrets.token_urlsafe(),
        )

    def _get(self, view, path, params):
        request = APIRequestFactory().get(path, params)
        force_authenticate(request, user=self.user)
        return view(request)

    def test_non_uuid_tool_id_on_default_profile_is_400(self):
        response = self._get(
            _DEFAULT_PROFILE,
            "/prompt-output/prompt-default-profile/",
            {"tool_id": "abc", "document_manager": str(uuid.uuid4())},
        )
        assert response.status_code == 400, response.data

    def test_non_uuid_document_manager_on_default_profile_is_400(self):
        response = self._get(
            _DEFAULT_PROFILE,
            "/prompt-output/prompt-default-profile/",
            {"tool_id": str(uuid.uuid4()), "document_manager": "abc"},
        )
        assert response.status_code == 400, response.data

    def test_absent_document_manager_on_default_profile_is_400(self):
        """An absent id would filter on NULL, rendering every prompt as "".

        A 200 with a blank body is indistinguishable from a project that has
        no outputs yet, so the caller has nothing to act on.
        """
        response = self._get(
            _DEFAULT_PROFILE,
            "/prompt-output/prompt-default-profile/",
            {"tool_id": str(uuid.uuid4())},
        )
        assert response.status_code == 400, response.data

    def test_non_uuid_tool_id_on_list_is_400(self):
        """The list action is the highest-traffic one on this viewset."""
        response = self._get(_LIST, "/prompt-output/", {"tool_id": "abc"})
        assert response.status_code == 400, getattr(response, "data", response)

    def test_non_uuid_tool_id_on_latest_by_keys_is_400(self):
        response = self._get(
            _LATEST_BY_KEYS,
            "/prompt-output/latest-by-keys/",
            {"tool_id": "abc", "prompt_keys": "a"},
        )
        assert response.status_code == 400, response.data

    def test_unresolvable_organization_is_not_served_as_empty(self):
        """Refuse rather than return a blank project that has real outputs."""
        UserContext.set_organization_identifier("org-that-does-not-exist")
        response = self._get(
            _DEFAULT_PROFILE,
            "/prompt-output/prompt-default-profile/",
            {"tool_id": str(uuid.uuid4()), "document_manager": str(uuid.uuid4())},
        )
        assert response.status_code >= 500, response.data


class ExtractionStatusEndpointTest(TestCase):
    """The internal callback endpoint must not report a failed write as 200.

    The worker never reads the body, so a 200 drops the status silently and
    every later Answer Prompt re-runs the full extraction.
    """

    URL = "/internal/v1/prompt-studio/extraction-status/"

    def _post(self, result):
        from prompt_studio.prompt_studio_core_v2 import internal_views

        payload = {
            "document_id": str(uuid.uuid4()),
            "profile_manager_id": str(uuid.uuid4()),
            "x2text_config_hash": "hash",
            "enable_highlight": False,
            "extracted": True,
        }
        request = APIRequestFactory().post(
            self.URL, json.dumps(payload), content_type="application/json"
        )
        with (
            patch.object(
                internal_views, "_parse_json_body", return_value=(payload, None)
            ),
            patch(
                "prompt_studio.prompt_profile_manager_v2.models.ProfileManager.objects"
            ) as profiles,
            patch(
                "prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper"
                ".PromptStudioIndexHelper.mark_extraction_status",
                return_value=result,
            ),
        ):
            profiles.get.return_value = object()
            return internal_views.extraction_status(request)

    def test_write_failure_is_a_retryable_500(self):
        assert self._post(ExtractionStatusResult.WRITE_FAILED).status_code == 500

    def test_missing_document_is_a_non_retryable_404(self):
        """500 is in the client's retry set; a gone document never comes back.

        Three retries with a 1s backoff factor would burn ~7s of worker sleep
        on a condition no retry can change.
        """
        assert self._post(ExtractionStatusResult.DOCUMENT_MISSING).status_code == 404

    def test_success_is_200(self):
        assert self._post(ExtractionStatusResult.OK).status_code == 200
