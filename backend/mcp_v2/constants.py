"""Constants for the hosted MCP server."""


class MCPServer:
    """Identity advertised to MCP clients during `initialize`."""

    NAME: str = "unstract"
    VERSION: str = "0.1.0"
    # Protocol revision this transport implements. Clients that request a
    # different revision are answered with this one, per the MCP spec's
    # version-negotiation rules.
    PROTOCOL_VERSION: str = "2024-11-05"


class JSONRPC:
    """JSON-RPC 2.0 wire constants."""

    VERSION: str = "2.0"

    # Standard error codes (JSON-RPC 2.0 spec).
    PARSE_ERROR: int = -32700
    INVALID_REQUEST: int = -32600
    METHOD_NOT_FOUND: int = -32601
    INVALID_PARAMS: int = -32602
    INTERNAL_ERROR: int = -32603

    # Implementation-defined codes (-32000 to -32099 reserved for servers).
    UNAUTHORIZED: int = -32001
    TOOL_EXECUTION_ERROR: int = -32002


class MCPMethod:
    """MCP methods handled by this transport."""

    INITIALIZE: str = "initialize"
    PING: str = "ping"
    TOOLS_LIST: str = "tools/list"
    TOOLS_CALL: str = "tools/call"

    # Notifications carry no `id` and expect no response body.
    NOTIFICATION_PREFIX: str = "notifications/"
