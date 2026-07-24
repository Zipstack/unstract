"""Resolved request context handed to MCP tool handlers.

Auth, organization resolution and deployment lookup all happen once in the
transport view. Tools receive the result and never repeat that work.
"""

from dataclasses import dataclass

from api_v2.models import APIDeployment


@dataclass(frozen=True)
class MCPContext:
    """Everything a tool needs about the caller's deployment.

    Attributes:
        api: The API deployment this MCP server session is scoped to.
        api_key: The validated API key used to authenticate the request.
            Carried through because downstream execution helpers record it
            against the execution.
        org_name: Organization identifier taken from the URL, matching the
            value already placed in the state store by the auth layer.
    """

    api: APIDeployment
    api_key: str
    org_name: str
