"""Guards that turn a malformed request into something the agent can act on.

Three layers, each covered here because each was added or changed without
coverage and each fails invisibly:

* ``valid_uuid`` — rejects an unparseable id *before* it reaches a UUID-typed
  ORM filter, where Django's field would raise ``ValidationError`` ahead of the
  call site's own ``is None`` check.
* the transport's JSON-RPC envelope guards — malformed body, non-object
  ``params``, and a preflight that raises something unexpected. Each exists to
  stop a Django 500 reaching a client that is parsing for an envelope.
* the platform view's CSRF gate — exempting only bearer-authenticated requests.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory

from mcp_server.constants import JSONRPC
from mcp_server.exceptions import MCPToolError
from mcp_server.registry import MCPTool, MCPToolRegistry
from mcp_server.sanitize import valid_uuid
from mcp_server.transport import BaseMCPView

GOOD_UUID = "88888888-8888-8888-8888-888888888888"


class ValidUuidTest(SimpleTestCase):
    def test_a_valid_uuid_passes_through_unchanged(self) -> None:
        assert valid_uuid(GOOD_UUID, "execution id", "hint") == GOOD_UUID

    def test_malformed_ids_are_agent_errors(self) -> None:
        for bad in ("not-a-uuid", "", "1234", None, 42):
            with self.subTest(bad):
                with self.assertRaises(MCPToolError) as caught:
                    valid_uuid(bad, "execution id", "Call listExecutions.")
                message = str(caught.exception)
                assert "not a valid execution id" in message
                # The hint is what makes this actionable rather than just a
                # refusal, so it is part of the contract.
                assert "Call listExecutions." in message

    def test_the_field_name_and_hint_reach_the_message(self) -> None:
        with self.assertRaises(MCPToolError) as caught:
            valid_uuid("x", "pipeline id", "Call listPipelines to see valid ids.")

        assert "pipeline id" in str(caught.exception)
        assert "listPipelines" in str(caught.exception)


class ExecutionScopeGuardTest(SimpleTestCase):
    """The call site refuses before touching the ORM."""

    def test_a_malformed_execution_id_never_reaches_the_filter(self) -> None:
        from mcp_server.tools.execution import get_execution_status

        context = MagicMock()
        context.api.workflow_id = "wf"

        with (
            patch(
                "mcp_server.tools.execution.WorkflowExecution.objects.filter"
            ) as scope_filter,
            patch(
                "mcp_server.tools.execution.ExecutionQuerySerializer.is_valid",
                return_value=True,
            ),
            patch(
                "mcp_server.tools.execution.ExecutionQuerySerializer.validated_data",
                {
                    "execution_id": "not-a-uuid",
                    "include_metadata": False,
                    "include_metrics": False,
                    "include_extracted_text": False,
                },
            ),
        ):
            with self.assertRaises(MCPToolError):
                get_execution_status(context, execution_id="not-a-uuid")

        scope_filter.assert_not_called()


class TransportEnvelopeGuardTest(SimpleTestCase):
    """Malformed input comes back as JSON-RPC, never as a Django error page."""

    def _view(self, registry=None):
        reg = registry or MCPToolRegistry()

        class Probe(BaseMCPView):
            authentication_classes: list = []
            permission_classes: list = []
            registry = reg

            def resolve_context(self, **kwargs):
                return MagicMock()

            def server_instructions(self, context):
                return ""

        return Probe.as_view()

    def _post(self, body: str):
        request = APIRequestFactory().post(
            "/mcp/", data=body, content_type="application/json"
        )
        return self._view()(request)

    def test_malformed_json_is_a_parse_error_envelope(self) -> None:
        """DRF would answer 400 with its own body; a JSON-RPC client is
        parsing for an envelope and would see a transport fault instead.
        """
        response = self._post("{not json")
        body = json.loads(response.content)

        assert body["error"]["code"] == JSONRPC.PARSE_ERROR
        # Unparseable input carries no id, so the spec requires null.
        assert body["id"] is None

    def test_non_object_params_is_an_invalid_params_envelope(self) -> None:
        """A JSON array is valid JSON-RPC and survives `or {}`, then reaches
        params.get() downstream as an AttributeError — a Django 500.
        """
        response = self._post(
            json.dumps(
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": [1, 2]}
            )
        )
        body = json.loads(response.content)

        assert body["error"]["code"] == JSONRPC.INVALID_PARAMS
        assert body["id"] == 1

    def test_a_scalar_params_is_also_refused(self) -> None:
        response = self._post(
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": "x"})
        )
        body = json.loads(response.content)

        assert body["error"]["code"] == JSONRPC.INVALID_PARAMS

    def test_absent_params_is_still_accepted(self) -> None:
        """`params` is optional — the guard must not reject its absence."""
        response = self._post(
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
        )
        body = json.loads(response.content)

        assert "error" not in body
        assert body["id"] == 3

    def test_a_preflight_raising_an_unexpected_error_stays_in_the_envelope(
        self,
    ) -> None:
        """A resolver filtering a UUID column by a malformed string raises
        Django ValidationError. Before the catch-all it escaped post() and the
        client got no envelope at all.
        """
        from django.core.exceptions import ValidationError

        def exploding_preflight(context, **kwargs):
            raise ValidationError("bad uuid")

        registry = MCPToolRegistry()
        registry.register(
            MCPTool(
                name="probeTool",
                description="",
                input_schema={"type": "object", "properties": {}},
                handler=lambda context, **kw: {"ok": True},
                preflight=exploding_preflight,
            )
        )

        request = APIRequestFactory().post(
            "/mcp/",
            data=json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "probeTool", "arguments": {}},
                }
            ),
            content_type="application/json",
        )
        response = self._view(registry)(request)
        body = json.loads(response.content)

        assert body["error"]["code"] == JSONRPC.TOOL_EXECUTION_ERROR
        assert body["id"] == 4


class PlatformCsrfGateTest(SimpleTestCase):
    """CSRF is waived for the bearer key, not for everything.

    ``CustomAuthMiddleware`` falls through to session auth on this path, so an
    unconditional exemption would let a logged-in browser session reach the
    org-wide write and billable surface with CSRF off.
    """

    def _initialize(self, with_key: bool):
        from mcp_server.platform_views import PlatformMCPServerView

        request = APIRequestFactory().post("/api/v1/unstract/org/mcp/", data={})
        if with_key:
            request.platform_api_key = MagicMock()

        view = PlatformMCPServerView()
        view.initialize_request(request)
        return request

    def test_a_bearer_request_is_exempt(self) -> None:
        request = self._initialize(with_key=True)

        assert getattr(request, "csrf_processing_done", False) is True

    def test_a_session_request_is_not_exempt(self) -> None:
        request = self._initialize(with_key=False)

        assert getattr(request, "csrf_processing_done", False) is not True
