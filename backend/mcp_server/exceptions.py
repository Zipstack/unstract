"""Exceptions raised by MCP tool handlers."""


class MCPToolError(Exception):
    """A tool failed in a way the calling agent can understand and act on.

    Raised for conditions the agent could plausibly recover from — bad
    arguments, an inactive deployment, a rate limit. The transport turns these
    into a JSON-RPC error carrying the message verbatim, so the message is
    prompt-facing: state what went wrong and what the agent should do next.

    Unexpected exceptions are deliberately *not* funnelled through this type;
    they are logged and reported generically so internal detail does not leak
    to the client.
    """
