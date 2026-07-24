"""Critical path ``mcp-server-auth``: the hosted MCP endpoint rejects
unauthenticated callers before any tool runs.

``POST /mcp/<org>/<api_name>/`` is unauthenticated at the DRF layer — like the
deployment execution endpoint it mirrors, it is guarded entirely by the API key
check inside the view. A regression there exposes every registered tool,
including the one that spends the organization's extraction quota. These tests
assert rejection lands before the tool handler is reached. Needs a live DB
(integration tier).
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import patch

import pytest
from account_v2.models import Organization
from api_v2.models import APIDeployment, APIKey
from django.test import TestCase
from rest_framework.test import APIRequestFactory
from utils.user_context import UserContext
from workflow_manager.workflow_v2.models.workflow import Workflow

from mcp_v2.views import MCPServerView

ORG_ID = "org-mcp"


def rpc_body(response):
    """Decode the JSON-RPC envelope from a rendered response."""
    return json.loads(response.content)


class MCPServerAuthTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(
            name=ORG_ID, display_name="Org MCP", organization_id=ORG_ID
        )
        UserContext.set_organization_identifier(ORG_ID)
        workflow = Workflow.objects.create(workflow_name="wf-mcp", is_active=True)

        self.api = APIDeployment.objects.create(api_name="live-api", workflow=workflow)
        self.key = APIKey.objects.create(api=self.api)
        self.inactive_key = APIKey.objects.create(api=self.api, is_active=False)

        self.inactive_api = APIDeployment.objects.create(
            api_name="dead-api", workflow=workflow, is_active=False
        )
        self.other_api = APIDeployment.objects.create(
            api_name="other-api", workflow=workflow
        )
        self.other_key = APIKey.objects.create(api=self.other_api)

        self.view = MCPServerView.as_view()
        self.factory = APIRequestFactory()

    def _post(
        self,
        api_name: str,
        auth: str | None,
        org: str = ORG_ID,
        payload: dict | None = None,
        path_key: str | None = None,
    ):
        headers = {"HTTP_AUTHORIZATION": auth} if auth is not None else {}
        body = payload if payload is not None else {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }
        request = self.factory.post(
            f"/mcp/{org}/{api_name}/", body, format="json", **headers
        )
        kwargs = {"org_name": org, "api_name": api_name}
        if path_key is not None:
            kwargs["api_key"] = path_key
        return self.view(request, **kwargs)

    @pytest.mark.critical_path("mcp-server-auth")
    @patch("mcp_v2.views.TOOL_REGISTRY.get")
    def test_bad_credentials_rejected_before_dispatch(self, registry_get) -> None:
        cases = [
            ("missing header", "live-api", None, ORG_ID),
            ("no bearer prefix", "live-api", f"Token {self.key.api_key}", ORG_ID),
            ("empty bearer", "live-api", "Bearer ", ORG_ID),
            ("unknown key", "live-api", f"Bearer {uuid.uuid4()}", ORG_ID),
            ("not a uuid", "live-api", "Bearer not-a-uuid", ORG_ID),
            ("inactive key", "live-api", f"Bearer {self.inactive_key.api_key}", ORG_ID),
            (
                "key of another api",
                "live-api",
                f"Bearer {self.other_key.api_key}",
                ORG_ID,
            ),
            ("unknown api", "ghost-api", f"Bearer {self.key.api_key}", ORG_ID),
            ("inactive api", "dead-api", f"Bearer {self.key.api_key}", ORG_ID),
            ("wrong org", "live-api", f"Bearer {self.key.api_key}", "no-such-org"),
        ]
        for label, api_name, auth, org in cases:
            with self.subTest(label):
                response = self._post(api_name, auth, org)
                assert response.status_code == 401, response.content
                assert rpc_body(response)["error"]["code"] == -32001

        registry_get.assert_not_called()

    @pytest.mark.critical_path("mcp-server-auth")
    def test_valid_key_reaches_tool_listing(self) -> None:
        """Guard the inverse: a check that rejected everything would pass all
        the rejection cases above.
        """
        response = self._post("live-api", f"Bearer {self.key.api_key}")

        assert response.status_code == 200, response.content
        tools = rpc_body(response)["result"]["tools"]
        assert [tool["name"] for tool in tools] == [
            "readMeFirst",
            "getApiInfo",
            "extractDocument",
            "getExecutionStatus",
        ]

    @pytest.mark.critical_path("mcp-server-auth")
    def test_api_key_in_url_path_authenticates(self) -> None:
        """The path-key route exists for MCP clients that cannot set headers;
        it must enforce exactly the same check as the header route.
        """
        ok = self._post("live-api", auth=None, path_key=str(self.key.api_key))
        assert ok.status_code == 200, ok.content

        rejected = self._post("live-api", auth=None, path_key=str(uuid.uuid4()))
        assert rejected.status_code == 401, rejected.content

    @pytest.mark.critical_path("mcp-server-auth")
    def test_path_key_wins_over_valid_header(self) -> None:
        """The path key takes precedence, so a bad path key must not be
        rescued by a good header — otherwise the precedence rule would be a
        way to smuggle an unchecked credential past the check.
        """
        response = self._post(
            "live-api",
            auth=f"Bearer {self.key.api_key}",
            path_key=str(uuid.uuid4()),
        )
        assert response.status_code == 401, response.content

    @pytest.mark.critical_path("mcp-server-auth")
    def test_get_probe_does_not_leak_deployment_details(self) -> None:
        """The unauthenticated GET probe advertises the server, not the
        deployment behind it.
        """
        request = self.factory.get(f"/mcp/{ORG_ID}/live-api/")
        response = self.view(request, org_name=ORG_ID, api_name="live-api")

        assert response.status_code == 200
        assert response.data["name"] == "unstract"
        assert "live-api" not in json.dumps(response.data)
