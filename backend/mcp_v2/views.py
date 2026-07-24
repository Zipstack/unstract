"""JSON-RPC 2.0 transport for the hosted Unstract MCP server.

Mirrors the shape of the API deployment execution endpoint: the URL carries the
organization and the deployment name, and the deployment's own API key
authenticates the caller. An MCP session is therefore scoped to exactly one API
deployment, and reuses that deployment's existing key management.
"""

import json
import logging
from typing import Any

from api_v2.deployment_helper import DeploymentHelper
from django.http import JsonResponse
from rest_framework import status, views
from rest_framework.request import Request
from rest_framework.response import Response

from mcp_v2.constants import JSONRPC, MCPMethod, MCPServer
from mcp_v2.context import MCPContext
from mcp_v2.exceptions import MCPToolError
from mcp_v2.registry import TOOL_REGISTRY

logger = logging.getLogger(__name__)


def _rpc_result(request_id: Any, result: Any) -> JsonResponse:
    """Build a JSON-RPC success response.

    JsonResponse rather than DRF's Response so the body is emitted verbatim:
    content negotiation must not turn a JSON-RPC envelope into the browsable
    API renderer for a client that sent a permissive Accept header.
    """
    return JsonResponse({"jsonrpc": JSONRPC.VERSION, "id": request_id, "result": result})


def _rpc_error(
    request_id: Any, code: int, message: str, data: Any = None
) -> JsonResponse:
    """Build a JSON-RPC error response.

    Always HTTP 200: transport-level success with an application-level error is
    exactly what JSON-RPC models, and clients read the envelope, not the status
    code. The one exception is authentication, which must be a real 401 so MCP
    clients can react to it (see `_auth_error`).
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JsonResponse({"jsonrpc": JSONRPC.VERSION, "id": request_id, "error": error})


def _auth_error(message: str) -> JsonResponse:
    """Build a 401 for a failed or missing credential.

    Unlike other failures this carries a real HTTP status, because a client
    that cannot authenticate needs to distinguish "wrong key" from "tool
    failed" before it has a usable session.
    """
    response = JsonResponse(
        {
            "jsonrpc": JSONRPC.VERSION,
            "id": None,
            "error": {"code": JSONRPC.UNAUTHORIZED, "message": message},
        },
        status=status.HTTP_401_UNAUTHORIZED,
    )
    response["WWW-Authenticate"] = 'Bearer realm="unstract-mcp"'
    return response


class MCPServerView(views.APIView):
    """MCP JSON-RPC endpoint for a single API deployment.

    Authentication is the deployment's API key, accepted either as a bearer
    token or — for MCP clients that cannot attach custom headers — as a path
    segment. This is a public, key-authenticated endpoint like the deployment
    execution endpoint it sits beside, so session auth does not apply.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def initialize_request(self, request: Request, *args: Any, **kwargs: Any) -> Request:
        """Skip CSRF, matching the public API deployment endpoint."""
        request.csrf_processing_done = True
        return super().initialize_request(request, *args, **kwargs)

    def get(
        self, request: Request, org_name: str, api_name: str, api_key: str | None = None
    ) -> Response:
        """Advertise server identity.

        Clients probe with GET to check connectivity before opening a session.
        Deliberately unauthenticated and free of deployment detail — it reveals
        only that an MCP server is mounted here.
        """
        return Response(
            {
                "name": MCPServer.NAME,
                "version": MCPServer.VERSION,
                "protocolVersion": MCPServer.PROTOCOL_VERSION,
                "transport": "http",
                "authMethods": ["bearer"],
            }
        )

    def post(
        self, request: Request, org_name: str, api_name: str, api_key: str | None = None
    ) -> JsonResponse:
        """Handle a single JSON-RPC request."""
        # `api_key` in the path takes precedence when present; otherwise fall
        # back to the Authorization header.
        if not api_key:
            header = request.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                api_key = header.split(" ", 1)[1].strip()

        if not api_key:
            return _auth_error("Missing API key")

        context = self._resolve_context(
            org_name=org_name, api_name=api_name, api_key=api_key
        )
        if context is None:
            return _auth_error("Invalid API key or unknown API deployment")

        body = request.data
        if not isinstance(body, dict):
            # Batch requests are a valid part of JSON-RPC 2.0 but are not used
            # by MCP clients; rejecting them explicitly beats a confusing
            # downstream AttributeError.
            return _rpc_error(
                None,
                JSONRPC.INVALID_REQUEST,
                "Invalid Request",
                "Expected a single JSON-RPC object",
            )

        request_id = body.get("id")
        method = body.get("method")

        if body.get("jsonrpc") != JSONRPC.VERSION:
            return _rpc_error(
                request_id,
                JSONRPC.INVALID_REQUEST,
                "Invalid Request",
                "Only JSON-RPC 2.0 is supported",
            )
        if not method:
            return _rpc_error(
                request_id, JSONRPC.INVALID_REQUEST, "Invalid Request", "Missing method"
            )

        return self._dispatch(
            method=method,
            request_id=request_id,
            params=body.get("params") or {},
            context=context,
        )

    def _resolve_context(
        self, org_name: str, api_name: str, api_key: str
    ) -> MCPContext | None:
        """Authenticate the key against the named deployment.

        Returns None for every failure mode — unknown deployment, wrong key,
        malformed key — so the caller answers all of them identically and the
        endpoint cannot be used to probe which deployment names exist.
        """
        # Pin the organization before touching org-scoped managers; the
        # deployment lookup below filters on it.
        DeploymentHelper.validate_parameters(
            self.request, api_name=api_name, org_name=org_name
        )

        api_deployment = DeploymentHelper.get_deployment_by_api_name(api_name=api_name)
        try:
            DeploymentHelper.validate_api(api_deployment=api_deployment, api_key=api_key)
        except Exception as error:
            logger.warning(
                f"MCP auth rejected for org '{org_name}', api '{api_name}': {error}"
            )
            return None

        return MCPContext(api=api_deployment, api_key=api_key, org_name=org_name)

    def _dispatch(
        self, method: str, request_id: Any, params: dict[str, Any], context: MCPContext
    ) -> JsonResponse:
        """Route a JSON-RPC method to its handler."""
        if method == MCPMethod.INITIALIZE:
            return _rpc_result(
                request_id,
                {
                    "protocolVersion": MCPServer.PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": MCPServer.NAME,
                        "version": MCPServer.VERSION,
                    },
                    "instructions": (
                        "Unstract runs LLM-driven extraction over unstructured "
                        "documents and returns structured JSON. This server is "
                        "scoped to the API deployment "
                        f"'{context.api.display_name}'. Call readMeFirst before "
                        "any other tool."
                    ),
                },
            )

        if method.startswith(MCPMethod.NOTIFICATION_PREFIX):
            # Notifications (e.g. notifications/initialized) carry no id and
            # must not receive a result body.
            return JsonResponse({}, status=status.HTTP_202_ACCEPTED)

        if method == MCPMethod.PING:
            return _rpc_result(request_id, {})

        if method == MCPMethod.TOOLS_LIST:
            return _rpc_result(request_id, {"tools": TOOL_REGISTRY.list_schemas()})

        if method == MCPMethod.TOOLS_CALL:
            return self._call_tool(request_id=request_id, params=params, context=context)

        return _rpc_error(
            request_id,
            JSONRPC.METHOD_NOT_FOUND,
            "Method not found",
            f"Unsupported method '{method}'",
        )

    def _call_tool(
        self, request_id: Any, params: dict[str, Any], context: MCPContext
    ) -> JsonResponse:
        """Invoke a registered tool and wrap its result in MCP content format."""
        tool_name = params.get("name")
        if not tool_name:
            return _rpc_error(
                request_id, JSONRPC.INVALID_PARAMS, "Invalid params", "Missing tool name"
            )

        tool = TOOL_REGISTRY.get(tool_name)
        if tool is None:
            return _rpc_error(
                request_id,
                JSONRPC.METHOD_NOT_FOUND,
                "Method not found",
                f"Tool '{tool_name}' not found. Available tools: {TOOL_REGISTRY.names()}",
            )

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _rpc_error(
                request_id,
                JSONRPC.INVALID_PARAMS,
                "Invalid params",
                "'arguments' must be an object",
            )

        try:
            result = tool.handler(context, **arguments)
        except MCPToolError as error:
            # Expected, agent-actionable failure: the message is written for
            # the agent, so pass it through as an error result rather than a
            # protocol error. isError=True lets the agent see and retry it.
            return _rpc_result(request_id, _tool_content(str(error), is_error=True))
        except TypeError as error:
            # Almost always the agent passing arguments the tool does not
            # accept; report it as bad params rather than a server fault.
            logger.warning(f"MCP tool '{tool_name}' called with bad arguments: {error}")
            return _rpc_error(
                request_id, JSONRPC.INVALID_PARAMS, "Invalid params", str(error)
            )
        except Exception as error:
            logger.exception(f"MCP tool '{tool_name}' failed: {error}")
            return _rpc_error(
                request_id,
                JSONRPC.TOOL_EXECUTION_ERROR,
                "Tool execution failed",
                f"Tool '{tool_name}' failed unexpectedly. "
                "Contact your Unstract administrator if this persists.",
            )

        return _rpc_result(
            request_id, _tool_content(json.dumps(result, indent=2, default=str))
        )


def _tool_content(text: str, is_error: bool = False) -> dict[str, Any]:
    """Wrap tool output in the MCP `tools/call` content envelope."""
    return {"content": [{"type": "text", "text": text}], "isError": is_error}
