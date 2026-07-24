"""JSON-RPC protocol behaviour of the hosted MCP server.

Auth is stubbed here so these stay in the unit tier; the auth boundary itself
is covered by ``test_mcp_auth``. What is checked is the wire contract an MCP
client depends on: envelope shape, method routing, and the error mapping that
decides whether a client retries, re-prompts, or gives up.
"""

from __future__ import annotations

import json
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from mcp_v2.constants import JSONRPC, MCPServer
from mcp_v2.context import MCPContext
from mcp_v2.exceptions import MCPToolError
from mcp_v2.registry import TOOL_REGISTRY
from mcp_v2.views import MCPServerView

ORG_ID = "org-mcp"
API_NAME = "live-api"


class FakeWorkflow:
    id = "11111111-1111-1111-1111-111111111111"
    workflow_name = "wf-mcp"


class FakeAPI:
    """Stands in for an APIDeployment so these tests need no database."""

    id = "22222222-2222-2222-2222-222222222222"
    display_name = "Invoice Extractor"
    api_name = API_NAME
    description = "Extracts invoice fields"
    is_active = True
    workflow = FakeWorkflow()
    workflow_id = FakeWorkflow.id


class MCPProtocolTest(SimpleTestCase):
    def setUp(self) -> None:
        self.view = MCPServerView.as_view()
        self.factory = APIRequestFactory()
        self.context = MCPContext(
            api=FakeAPI(), api_key="test-key", org_name=ORG_ID
        )

    def _failing_tool(self, error: Exception, name: str = "getApiInfo"):
        """Swap a registered tool for one that raises.

        The registry stores handler references captured at import, so patching
        the tool's module attribute would not affect an already-built registry —
        the substitution has to happen at the registry lookup.
        """
        from dataclasses import replace

        def boom(*args, **kwargs):
            raise error

        original = TOOL_REGISTRY.get(name)
        return patch.object(
            TOOL_REGISTRY, "get", return_value=replace(original, handler=boom)
        )

    def _call(self, body):
        """POST a JSON-RPC body with auth stubbed out."""
        request = self.factory.post(f"/mcp/{ORG_ID}/{API_NAME}/", body, format="json")
        with patch.object(
            MCPServerView, "_resolve_context", return_value=self.context
        ):
            response = self.view(
                request, org_name=ORG_ID, api_name=API_NAME, api_key="test-key"
            )
        return response, json.loads(response.content)

    def test_initialize_returns_protocol_and_server_info(self) -> None:
        response, body = self._call(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        )

        assert response.status_code == 200
        assert body["id"] == 1
        result = body["result"]
        assert result["protocolVersion"] == MCPServer.PROTOCOL_VERSION
        assert result["serverInfo"]["name"] == MCPServer.NAME
        # The agent is told which deployment it is attached to, so it does not
        # have to guess what the tools will operate on.
        assert "Invoice Extractor" in result["instructions"]

    def test_notification_gets_no_result_body(self) -> None:
        """Notifications carry no id; answering one with a result would be a
        protocol violation that some clients treat as a fatal error.
        """
        response, body = self._call(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )

        assert response.status_code == 202
        assert body == {}

    def test_ping_returns_empty_result(self) -> None:
        _, body = self._call({"jsonrpc": "2.0", "id": 7, "method": "ping"})
        assert body["result"] == {}

    def test_wrong_jsonrpc_version_rejected(self) -> None:
        _, body = self._call({"jsonrpc": "1.0", "id": 1, "method": "ping"})
        assert body["error"]["code"] == JSONRPC.INVALID_REQUEST

    def test_missing_method_rejected(self) -> None:
        _, body = self._call({"jsonrpc": "2.0", "id": 1})
        assert body["error"]["code"] == JSONRPC.INVALID_REQUEST

    def test_unknown_method_rejected(self) -> None:
        _, body = self._call(
            {"jsonrpc": "2.0", "id": 1, "method": "resources/list"}
        )
        assert body["error"]["code"] == JSONRPC.METHOD_NOT_FOUND

    def test_unknown_tool_lists_available_tools(self) -> None:
        """The error names the real tools, so a mistaken agent can correct
        itself without another round trip.
        """
        _, body = self._call(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "deleteEverything"},
            }
        )

        assert body["error"]["code"] == JSONRPC.METHOD_NOT_FOUND
        assert "readMeFirst" in body["error"]["data"]

    def test_tool_result_is_wrapped_in_mcp_content(self) -> None:
        _, body = self._call(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "getApiInfo", "arguments": {}},
            }
        )

        result = body["result"]
        assert result["isError"] is False
        payload = json.loads(result["content"][0]["text"])
        assert payload["display_name"] == "Invoice Extractor"
        assert payload["workflow"]["name"] == "wf-mcp"

    def test_tool_error_returns_actionable_result_not_protocol_error(self) -> None:
        """An MCPToolError is the agent's problem to fix, so it comes back as
        an isError result the agent can read — not a protocol error, which
        many clients surface as an unrecoverable transport fault.
        """
        with self._failing_tool(MCPToolError("Deployment is not active")):
            _, body = self._call(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "getApiInfo", "arguments": {}},
                }
            )

        assert "error" not in body
        assert body["result"]["isError"] is True
        assert "not active" in body["result"]["content"][0]["text"]

    def test_unexpected_tool_failure_does_not_leak_internals(self) -> None:
        with self._failing_tool(
            RuntimeError("psycopg2 connection string user=admin")
        ):
            _, body = self._call(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "getApiInfo", "arguments": {}},
                }
            )

        assert body["error"]["code"] == JSONRPC.TOOL_EXECUTION_ERROR
        assert "psycopg2" not in json.dumps(body)

    def test_unexpected_argument_reported_as_invalid_params(self) -> None:
        _, body = self._call(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "getApiInfo", "arguments": {"nope": 1}},
            }
        )

        assert body["error"]["code"] == JSONRPC.INVALID_PARAMS

    def test_batch_request_rejected(self) -> None:
        request = self.factory.post(
            f"/mcp/{ORG_ID}/{API_NAME}/",
            [{"jsonrpc": "2.0", "id": 1, "method": "ping"}],
            format="json",
        )
        with patch.object(
            MCPServerView, "_resolve_context", return_value=self.context
        ):
            response = self.view(
                request, org_name=ORG_ID, api_name=API_NAME, api_key="test-key"
            )

        body = json.loads(response.content)
        assert body["error"]["code"] == JSONRPC.INVALID_REQUEST
