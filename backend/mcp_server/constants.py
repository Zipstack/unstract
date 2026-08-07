"""Constants for the hosted MCP server."""


class MCPServer:
    """Identity advertised to MCP clients during `initialize`."""

    NAME: str = "unstract"
    VERSION: str = "0.1.0"

    # Protocol revision this transport implements, and the one offered to a
    # client that asks for something unsupported. This is 2025-06-18 because
    # that is the revision whose rules the transport actually follows —
    # Streamable HTTP, and answering GET with 405 rather than an SSE stream.
    PROTOCOL_VERSION: str = "2025-06-18"

    # Revisions this server will speak if a client asks for one by name.
    #
    # 2024-11-05 is kept because the request/response subset used here — the
    # `initialize` handshake, `tools/list`, `tools/call` and `ping` — is
    # unchanged between the two, and a client pinned to it works against this
    # server today. What differs is the parts this server does not implement
    # anyway (server-initiated streaming, session ids), so accepting the older
    # revision costs nothing and disconnects no one.
    #
    # Ordered newest first: `initialize` echoes the client's revision when it
    # appears here, and otherwise offers the first entry.
    SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-06-18", "2024-11-05")


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

    # Canonical `message` for each code. The JSON-RPC 2.0 spec fixes these
    # strings, and a client may match on them, so they are defined once beside
    # the code they belong to rather than repeated at each raise site.
    MSG_PARSE_ERROR: str = "Parse error"
    MSG_INVALID_REQUEST: str = "Invalid Request"
    MSG_METHOD_NOT_FOUND: str = "Method not found"
    MSG_INVALID_PARAMS: str = "Invalid params"
    MSG_INTERNAL_ERROR: str = "Internal error"


class MCPMethod:
    """MCP methods handled by this transport."""

    INITIALIZE: str = "initialize"
    PING: str = "ping"
    TOOLS_LIST: str = "tools/list"
    TOOLS_CALL: str = "tools/call"

    # Notifications carry no `id` and expect no response body.
    NOTIFICATION_PREFIX: str = "notifications/"
