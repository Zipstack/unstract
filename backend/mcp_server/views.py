"""Deployment-scoped MCP server.

Mirrors the shape of the API deployment execution endpoint: the URL carries the
organization and the deployment name, and the deployment's own API key
authenticates the caller. An MCP session is therefore scoped to exactly one API
deployment, and reuses that deployment's existing key management.

This endpoint is in ``WHITELISTED_PATHS``, so ``CustomAuthMiddleware`` skips it
and the view owns its own authentication — deliberately, because a deployment
key is not a platform key and must not resolve to a user.
"""

import logging
from typing import Any

from api_v2.deployment_helper import DeploymentHelper
from rest_framework.request import Request

from mcp_server.context import MCPContext
from mcp_server.registry import DEPLOYMENT_TOOLS
from mcp_server.transport import BaseMCPView

logger = logging.getLogger(__name__)


class MCPServerView(BaseMCPView):
    """MCP JSON-RPC endpoint for a single API deployment.

    Authentication is the deployment's API key, accepted either as a bearer
    token or — for MCP clients that cannot attach custom headers — as a path
    segment. This is a public, key-authenticated endpoint like the deployment
    execution endpoint it sits beside, so session auth does not apply.
    """

    registry = DEPLOYMENT_TOOLS

    authentication_classes: list = []
    permission_classes: list = []

    def initialize_request(self, request: Request, *args: Any, **kwargs: Any) -> Request:
        """Skip CSRF, matching the public API deployment endpoint."""
        request.csrf_processing_done = True
        return super().initialize_request(request, *args, **kwargs)

    def auth_failure_message(self) -> str:
        return "Invalid API key or unknown API deployment"

    def server_instructions(self, context: MCPContext) -> str:
        return (
            "Unstract runs LLM-driven extraction over unstructured documents "
            "and returns structured JSON. This server is scoped to the API "
            f"deployment '{context.api.display_name}'. Call readMeFirst before "
            "any other tool."
        )

    def resolve_context(
        self,
        request: Request,
        org_name: str,
        api_name: str,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> MCPContext | None:
        """Authenticate the key against the named deployment.

        Returns None for every failure mode — unknown deployment, wrong key,
        malformed key — so the caller answers all of them identically and the
        endpoint cannot be used to probe which deployment names exist.
        """
        # `api_key` in the path takes precedence when present; otherwise fall
        # back to the Authorization header.
        if not api_key:
            header = request.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                api_key = header.split(" ", 1)[1].strip()

        if not api_key:
            return None

        # Pin the organization before touching org-scoped managers; the
        # deployment lookup below filters on it.
        DeploymentHelper.validate_parameters(
            request, api_name=api_name, org_name=org_name
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
