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

from mcp_server.views import MCPServerView

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
    ):
        headers = {"HTTP_AUTHORIZATION": auth} if auth is not None else {}
        body = (
            payload
            if payload is not None
            else {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
            }
        )
        request = self.factory.post(
            f"/deployment/api/{org}/{api_name}/mcp", body, format="json", **headers
        )
        return self.view(request, org_name=org, api_name=api_name)

    @pytest.mark.critical_path("mcp-server-auth")
    @patch("mcp_server.registry.DEPLOYMENT_TOOLS.get")
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
    def test_no_route_accepts_the_api_key_in_the_url(self) -> None:
        """The credential travels in a header, never in the path.

        An earlier revision offered `/mcp/<api_key>/` for "clients that cannot
        set headers". That class does not exist for HTTP transports — the spec
        requires `Authorization` on every authenticated request and forbids
        tokens in the URI — while a key in the path reaches access logs, APM
        traces and intermediaries a header never touches.

        Asserted at the URL layer rather than the view: a route resolving here
        again is the regression, and it would not be caught by the view alone.
        """
        from django.urls import Resolver404, resolve

        base = f"/deployment/api/{ORG_ID}/live-api"

        with self.assertRaises(Resolver404):
            resolve(f"{base}/mcp/{self.key.api_key}/")
        with self.assertRaises(Resolver404):
            resolve(f"{base}/mcp/{uuid.uuid4()}")

        # The header route still works, so this is a narrowing rather than a
        # break.
        assert resolve(f"{base}/mcp").url_name == "mcp_server"

    @pytest.mark.critical_path("mcp-server-auth")
    def test_a_key_in_the_path_does_not_authenticate(self) -> None:
        """Belt and braces: even if a route were re-added, the view ignores it.

        `resolve_context` reads the bearer header only, so a caller supplying
        the key some other way is rejected like any unauthenticated request.
        """
        request = self.factory.post(
            f"/deployment/api/{ORG_ID}/live-api/mcp/{self.key.api_key}/",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            format="json",
        )
        response = self.view(request, org_name=ORG_ID, api_name="live-api")

        assert response.status_code == 401, response.content

    @pytest.mark.critical_path("mcp-server-auth")
    def test_mcp_url_hangs_off_the_execution_url(self) -> None:
        """Pins the endpoint's address and its relationship to the REST one.

        The MCP endpoint is a suffix on the deployment's own execution URL, so
        the two are visibly the same resource. It must also stay inside the
        whitelisted deployment prefix: this server authenticates a deployment
        key itself, and routing it somewhere the session middleware applies
        would break every client.
        """
        from django.conf import settings
        from django.test import Client
        from django.urls import resolve

        base = f"/deployment/api/{ORG_ID}/live-api"

        assert resolve(f"{base}/mcp").url_name == "mcp_server"
        # The execution endpoint must still resolve to execution, not MCP.
        assert resolve(f"{base}/").url_name == "api_deployment_execution"

        assert any(
            f"{base}/mcp".startswith(path) for path in settings.WHITELISTED_PATHS
        ), "deployment MCP path must stay inside the whitelisted deployment prefix"

        # And it must really answer there, not merely resolve.
        response = Client().post(
            f"{base}/mcp",
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.key.api_key}",
        )
        assert response.status_code == 200, response.content
        assert "readMeFirst" in response.content.decode()

    @pytest.mark.critical_path("mcp-server-auth")
    def test_get_probe_does_not_leak_deployment_details(self) -> None:
        """The unauthenticated GET probe advertises the server, not the
        deployment behind it.

        It answers 405: a Streamable HTTP client issues GET to open an SSE
        stream, and this server pushes nothing, so declining is the conformant
        response. The identity body rides along for uptime probes.

        ``Allow`` is asserted at the value DRF actually produces, not the
        ``"POST"`` a handler would like to set: ``finalize_response`` overwrites
        any handler value with ``self.allowed_methods``. In the real WSGI stack
        ``RemoveAllowHeaderMiddleware`` then pops the header entirely, but this
        test drives the view through ``APIRequestFactory``, which runs no
        middleware — so the header is visible here and worth pinning.
        """
        request = self.factory.get(f"/mcp/{ORG_ID}/live-api/")
        response = self.view(request, org_name=ORG_ID, api_name="live-api")
        body = json.loads(response.content)

        assert response.status_code == 405
        assert "POST" in response["Allow"]
        assert body["name"] == "unstract"
        # The whole rendered body, not just the parsed identity: the point of
        # this test is that nothing anywhere in the response names the tenant.
        assert "live-api" not in response.content.decode()
        assert ORG_ID not in response.content.decode()
