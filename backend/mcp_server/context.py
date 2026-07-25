"""Resolved request context handed to MCP tool handlers.

Auth, organization resolution and deployment lookup all happen once in the
transport view. Tools receive the result and never repeat that work.
"""

from dataclasses import dataclass
from typing import Any

from api_v2.models import APIDeployment


@dataclass(frozen=True)
class PlatformMCPContext:
    """Everything a tool needs about an organization-scoped caller.

    Built from what ``CustomAuthMiddleware`` already resolved — this server
    does not re-authenticate. Deliberately shares no base class with
    ``MCPContext``: the two servers expose disjoint tool sets, and a common
    base would invite a tool to be written against whichever fields happen to
    overlap.

    Attributes:
        user: The service-account user the platform key resolves to. Passed to
            org-scoped managers so tools inherit the platform's own sharing
            rules rather than reimplementing them.
        platform_key: The validated key, carried for its permission tier.
        org_name: Organization identifier from the URL, already validated
            against the key's own organization by the middleware.
        request: The DRF request. Carried because several platform helpers
            (notably ``PipelineManager.execute_pipeline``) take a request
            rather than a user and mutate ``request.data`` on the way through.
            Passing the real request is safer than fabricating one, since it
            keeps the org and auth state those helpers read.
    """

    user: Any
    platform_key: Any
    org_name: str
    request: Any = None


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
