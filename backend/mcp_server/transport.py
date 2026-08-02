"""Shared JSON-RPC 2.0 transport for the hosted MCP servers.

Two MCP servers are hosted from this app — one scoped to a single API
deployment, one scoped to an organization. They differ only in how a caller is
authenticated and which tools they expose; the wire protocol, dispatch and
error mapping are identical, and live here so the two cannot drift apart on
protocol behaviour.

Subclasses supply:
    registry              - the MCPToolRegistry to dispatch into
    resolve_context()     - authenticate, or return None to reject
    server_instructions() - the prose an agent reads on `initialize`
"""

import json
import logging
from typing import Any

from django.http import JsonResponse
from rest_framework import status, views
from rest_framework.exceptions import ParseError
from rest_framework.request import Request

from mcp_server.constants import JSONRPC, MCPMethod, MCPServer
from mcp_server.exceptions import MCPToolError
from mcp_server.registry import MCPToolRegistry
from mcp_server.sanitize import log_exception

logger = logging.getLogger(__name__)


def negotiate_protocol_version(requested: Any) -> str:
    """Choose the protocol revision to answer `initialize` with.

    The spec's rule is an echo, not an announcement: "If the server supports
    the requested protocol version, it MUST respond with the same version.
    Otherwise, the server MUST respond with another protocol version it
    supports" (rev 2025-06-18, Lifecycle → Version Negotiation).

    So a client asking for a revision this server speaks gets that revision
    back, and anything else — an unknown revision, a malformed value, or an
    omitted field — is answered with this server's preferred one. The client
    then decides whether it can live with that and disconnects if not, which
    is why an unsupported request is not an error response here.
    """
    if isinstance(requested, str) and requested in MCPServer.SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    if requested is not None:
        logger.info(
            f"MCP client requested unsupported protocol version {requested!r}; "
            f"offering {MCPServer.PROTOCOL_VERSION}"
        )
    return MCPServer.PROTOCOL_VERSION


def rpc_result(request_id: Any, result: Any) -> JsonResponse:
    """Build a JSON-RPC success response.

    JsonResponse rather than DRF's Response so the body is emitted verbatim:
    content negotiation must not turn a JSON-RPC envelope into the browsable
    API renderer for a client that sent a permissive Accept header.
    """
    return JsonResponse({"jsonrpc": JSONRPC.VERSION, "id": request_id, "result": result})


def rpc_error(request_id: Any, code: int, message: str, data: Any = None) -> JsonResponse:
    """Build a JSON-RPC error response.

    Always HTTP 200: transport-level success with an application-level error is
    exactly what JSON-RPC models, and clients read the envelope, not the status
    code. The one exception is authentication, which must be a real 401 so MCP
    clients can react to it (see `auth_error`).
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return JsonResponse({"jsonrpc": JSONRPC.VERSION, "id": request_id, "error": error})


def auth_error(
    message: str, http_status: int = status.HTTP_401_UNAUTHORIZED
) -> JsonResponse:
    """Build a 401/403 for a rejected credential.

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
        status=http_status,
    )
    if http_status == status.HTTP_401_UNAUTHORIZED:
        response["WWW-Authenticate"] = 'Bearer realm="unstract-mcp"'
    return response


def tool_content(text: str, is_error: bool = False) -> dict[str, Any]:
    """Wrap tool output in the MCP `tools/call` content envelope."""
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


class BaseMCPView(views.APIView):
    """JSON-RPC transport shared by the deployment and platform MCP servers."""

    #: Tools this server exposes. Set by each subclass.
    registry: MCPToolRegistry = None

    def get_registry(self) -> MCPToolRegistry:
        """Return the registry to dispatch into.

        Indirection exists so tests can patch a single seam rather than a
        module-level global shared by both servers.
        """
        return self.registry

    def resolve_context(self, **kwargs: Any) -> Any | None:
        """Authenticate the caller and build the per-request context.

        Return None to reject. Subclasses must answer every failure mode
        identically so the endpoint cannot be used to probe what exists.
        """
        raise NotImplementedError

    def server_instructions(self, context: Any) -> str:
        """Prose returned on `initialize`, read by the agent as a prompt."""
        raise NotImplementedError

    def auth_failure_message(self) -> str:
        """Message used for every rejected credential on this server."""
        return "Invalid or missing credentials"

    def server_info(self) -> dict[str, Any]:
        """Identity advertised on GET and on `initialize`."""
        return {
            "name": MCPServer.NAME,
            "version": MCPServer.VERSION,
            "protocolVersion": MCPServer.PROTOCOL_VERSION,
            "transport": "http",
            "authMethods": ["bearer"],
        }

    def get(self, request: Request, **kwargs: Any) -> JsonResponse:
        """Refuse the SSE stream, but say who is here.

        Under Streamable HTTP a client issues GET to open a server-to-client
        SSE stream, and a server that offers none must answer 405 (spec rev
        2025-06-18). Nothing here pushes messages — every tool call is
        request/response — so 405 is the honest answer, and returning
        ``200 application/json`` instead would leave a conformant client
        parsing an identity document as an event stream.

        The body is kept anyway: uptime checks and humans with curl probe this
        path, and a 405 may carry one. It stays deliberately free of tenant
        detail — it reveals only that an MCP server is mounted here.

        ``JsonResponse``, not DRF's ``Response``, for the same reason ``post``
        uses it: a DRF response runs content negotiation, so a client sending
        ``Accept: text/html`` would be handed the browsable-API renderer.

        No ``Allow`` header is set here. RFC 9110 asks for one on a 405, but a
        handler cannot control it and pretending otherwise misleads a reader:
        DRF's ``finalize_response`` overwrites any handler-set value with
        ``self.allowed_methods`` (``GET, POST, HEAD, OPTIONS``, since this view
        defines both verbs), and ``RemoveAllowHeaderMiddleware`` — global in
        ``MIDDLEWARE`` — then pops the header from every response before it
        leaves the process. So a client sees no ``Allow`` at all; a test driving
        the view through ``APIRequestFactory`` bypasses that middleware and sees
        DRF's value.
        """
        return JsonResponse(self.server_info(), status=405)

    def post(self, request: Request, **kwargs: Any) -> JsonResponse:
        """Handle a single JSON-RPC request."""
        context = self.resolve_context(request=request, **kwargs)
        if context is None:
            return auth_error(self.auth_failure_message())

        try:
            body = request.data
        except ParseError:
            # DRF would answer 400 with its own error body. A JSON-RPC client
            # is parsing for an envelope, so give it -32700 as the spec
            # requires; the id is null because unparseable input has none.
            return rpc_error(
                None,
                JSONRPC.PARSE_ERROR,
                "Parse error",
                "Request body is not valid JSON",
            )

        if not isinstance(body, dict):
            # Batch requests are valid JSON-RPC 2.0 but are not used by MCP
            # clients; rejecting them explicitly beats a confusing downstream
            # AttributeError.
            return rpc_error(
                None,
                JSONRPC.INVALID_REQUEST,
                "Invalid Request",
                "Expected a single JSON-RPC object",
            )

        request_id = body.get("id")
        method = body.get("method")

        if body.get("jsonrpc") != JSONRPC.VERSION:
            return rpc_error(
                request_id,
                JSONRPC.INVALID_REQUEST,
                "Invalid Request",
                "Only JSON-RPC 2.0 is supported",
            )
        if not method:
            return rpc_error(
                request_id, JSONRPC.INVALID_REQUEST, "Invalid Request", "Missing method"
            )

        # `params` is optional, but when present JSON-RPC allows an array or an
        # object and MCP uses only objects. A truthy non-dict survives `or {}`
        # and reaches `params.get(...)` downstream as an AttributeError, i.e. a
        # Django 500 rather than an envelope the client can read.
        params = body.get("params") or {}
        if not isinstance(params, dict):
            return rpc_error(
                request_id,
                JSONRPC.INVALID_PARAMS,
                "Invalid params",
                "'params' must be an object",
            )

        return self._dispatch(
            method=method,
            request_id=request_id,
            params=params,
            context=context,
        )

    def _dispatch(
        self, method: str, request_id: Any, params: dict[str, Any], context: Any
    ) -> JsonResponse:
        """Route a JSON-RPC method to its handler."""
        if method == MCPMethod.INITIALIZE:
            return rpc_result(
                request_id,
                {
                    "protocolVersion": negotiate_protocol_version(
                        params.get("protocolVersion")
                    ),
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": MCPServer.NAME,
                        "version": MCPServer.VERSION,
                    },
                    "instructions": self.server_instructions(context),
                },
            )

        if method.startswith(MCPMethod.NOTIFICATION_PREFIX):
            # Notifications (e.g. notifications/initialized) carry no id and
            # must not receive a result body.
            return JsonResponse({}, status=status.HTTP_202_ACCEPTED)

        if method == MCPMethod.PING:
            return rpc_result(request_id, {})

        if method == MCPMethod.TOOLS_LIST:
            return rpc_result(request_id, {"tools": self.get_registry().list_schemas()})

        if method == MCPMethod.TOOLS_CALL:
            return self._call_tool(request_id=request_id, params=params, context=context)

        return rpc_error(
            request_id,
            JSONRPC.METHOD_NOT_FOUND,
            "Method not found",
            f"Unsupported method '{method}'",
        )

    def check_tool_allowed(self, tool: Any, context: Any) -> str | None:
        """Authorize a specific tool for this caller.

        Return None to allow, or a message explaining the refusal. The default
        allows everything the registry exposes; servers with permission tiers
        override this.
        """
        return None

    def check_spend_allowed(self, tool: Any, context: Any) -> str | None:
        """Claim budget for a billable tool.

        Return None to allow, or a message explaining that the budget is spent.
        Called once per invocation immediately before the handler runs, so
        overriding servers should treat it as consuming, not merely checking.

        The default allows everything — the deployment server's costs are
        already bounded by the API deployment rate limiter.
        """
        return None

    def _call_tool(
        self, request_id: Any, params: dict[str, Any], context: Any
    ) -> JsonResponse:
        """Invoke a registered tool and wrap its result in MCP content format."""
        registry = self.get_registry()
        tool_name = params.get("name")
        if not tool_name:
            return rpc_error(
                request_id, JSONRPC.INVALID_PARAMS, "Invalid params", "Missing tool name"
            )

        tool = registry.get(tool_name)
        if tool is None:
            return rpc_error(
                request_id,
                JSONRPC.METHOD_NOT_FOUND,
                "Method not found",
                f"Tool '{tool_name}' not found. Available tools: {registry.names()}",
            )

        refusal = self.check_tool_allowed(tool, context)
        if refusal is not None:
            return rpc_error(
                request_id, JSONRPC.UNAUTHORIZED, "Permission denied", refusal
            )

        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return rpc_error(
                request_id,
                JSONRPC.INVALID_PARAMS,
                "Invalid params",
                "'arguments' must be an object",
            )

        # Validate the arguments a billable tool was given *before* claiming
        # budget. The budget is consumed on invocation and never refunded, so
        # without this a caller naming a deployment that does not exist would
        # pay a slot for a call that spent nothing upstream — and an agent
        # guessing at a name could exhaust the window without ever running a
        # single extraction.
        if tool.preflight is not None:
            try:
                tool.preflight(context, **arguments)
            except MCPToolError as error:
                return rpc_result(request_id, tool_content(str(error), is_error=True))
            except TypeError as error:
                logger.warning(
                    f"MCP tool '{tool_name}' preflight rejected arguments: {error}"
                )
                return rpc_error(
                    request_id, JSONRPC.INVALID_PARAMS, "Invalid params", str(error)
                )
            except Exception as error:
                # Same catch-all the handler path below has, and for the same
                # reason: a resolver filtering a UUID column by a malformed
                # string raises Django ValidationError, which would otherwise
                # escape post() and reach the client as a bare 500 with no
                # JSON-RPC envelope at all.
                log_exception(
                    logger, f"MCP tool '{tool_name}' preflight failed unexpectedly", error
                )
                return rpc_error(
                    request_id,
                    JSONRPC.TOOL_EXECUTION_ERROR,
                    "Tool execution failed",
                    f"Tool '{tool_name}' could not validate its arguments. "
                    "Contact your Unstract administrator if this persists.",
                )

        # Budget is checked after permission and preflight, and before the
        # handler, so neither an unauthorized call nor one that could never
        # have run consumes budget. Unlike the permission refusal above this is
        # temporal, so it comes back as an isError *result* the agent can read
        # and retry — a protocol error would read as "this tool does not work"
        # and stop it retrying later.
        over_budget = self.check_spend_allowed(tool, context)
        if over_budget is not None:
            return rpc_result(request_id, tool_content(over_budget, is_error=True))

        try:
            result = tool.handler(context, **arguments)
        except MCPToolError as error:
            # Expected, agent-actionable failure: the message is written for
            # the agent, so pass it through as an error result rather than a
            # protocol error. isError=True lets the agent see and retry it.
            return rpc_result(request_id, tool_content(str(error), is_error=True))
        except TypeError as error:
            # Almost always the agent passing arguments the tool does not
            # accept; report it as bad params rather than a server fault.
            logger.warning(f"MCP tool '{tool_name}' called with bad arguments: {error}")
            return rpc_error(
                request_id, JSONRPC.INVALID_PARAMS, "Invalid params", str(error)
            )
        except Exception as error:
            # Redacted: this catches *any* tool handler, so the exception can
            # come from a connector, a provider client or the execution stack —
            # all of which report credentials in their error text.
            log_exception(logger, f"MCP tool '{tool_name}' failed", error)
            return rpc_error(
                request_id,
                JSONRPC.TOOL_EXECUTION_ERROR,
                "Tool execution failed",
                f"Tool '{tool_name}' failed unexpectedly. "
                "Contact your Unstract administrator if this persists.",
            )

        return rpc_result(
            request_id, tool_content(json.dumps(result, indent=2, default=str))
        )
