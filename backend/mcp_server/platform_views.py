"""Organization-scoped MCP server.

Mounted on a tenant URL — deliberately *not* under the whitelisted ``/mcp/``
prefix — so ``CustomAuthMiddleware`` runs ahead of it and performs the
authentication. By the time this view executes, the middleware has already:

* resolved the ``Authorization: Bearer <uuid>`` platform key,
* rejected unknown, inactive, and wrong-organization keys,
* rejected keys whose permission tier disallows the HTTP method,
* set ``request.user`` to the key's service account and pinned
  ``ORGANIZATION_ID`` in the state store.

This view therefore reads that result rather than re-authenticating. Two
consequences worth stating plainly, because both are easy to get wrong:

1. ``authentication_classes`` must NOT be emptied here. The deployment server
   empties it because it owns its own auth; doing the same here is harmless
   only by accident, and setting DRF authenticators that return a user would
   actively override what the middleware resolved.
2. Because the auth lives in middleware, a test that calls this view through
   ``APIRequestFactory`` bypasses it entirely and would pass against a
   completely open endpoint. The auth-boundary tests go through the full URL
   stack for exactly this reason.
"""

import logging
from typing import Any

from platform_api.models import ApiKeyPermission
from rest_framework.request import Request

from mcp_server.context import PlatformMCPContext
from mcp_server.registry import PLATFORM_TOOLS
from mcp_server.transport import BaseMCPView

logger = logging.getLogger(__name__)


class PlatformMCPServerView(BaseMCPView):
    """MCP JSON-RPC endpoint scoped to an organization.

    Exposes read-only discovery tools over the organization's resources,
    authenticated by a platform API key.
    """

    registry = PLATFORM_TOOLS

    # Intentionally not overriding authentication_classes: the project sets no
    # DEFAULT_AUTHENTICATION_CLASSES that would resolve a user, so the
    # middleware's request.user survives into the view.
    permission_classes: list = []

    def initialize_request(self, request: Request, *args: Any, **kwargs: Any) -> Request:
        """Skip CSRF.

        The middleware already marks bearer-authenticated requests CSRF-exempt;
        this makes the view's behaviour explicit rather than dependent on that.
        """
        request.csrf_processing_done = True
        return super().initialize_request(request, *args, **kwargs)

    def auth_failure_message(self) -> str:
        return "A valid platform API key is required"

    def server_instructions(self, context: PlatformMCPContext) -> str:
        return (
            "Unstract runs LLM-driven extraction over unstructured documents "
            "and returns structured JSON. This server is scoped to the "
            f"organization '{context.org_name}' and is read-only: it discovers "
            "deployments, workflows and Prompt Studio projects but cannot run "
            "or change anything. Call readMeFirst before any other tool."
        )

    def resolve_context(
        self, request: Request, **kwargs: Any
    ) -> PlatformMCPContext | None:
        """Read the credential the auth middleware already resolved.

        Returns None when the middleware did not attach a platform key. That is
        a defence-in-depth check rather than the primary gate: an unauthenticated
        request should never reach this view, because the middleware rejects it
        first with its own 401. If it does reach here — a whitelist edit, a
        routing change — refusing is the safe answer.
        """
        platform_key = getattr(request, "platform_api_key", None)
        user = getattr(request, "user", None)

        # The organization is not a URL kwarg here: the tenant prefix consumes
        # it, and OrganizationMiddleware parses it onto the request. Read it
        # from there rather than from the route.
        org_name = getattr(request, "organization_id", None)

        if platform_key is None or user is None or not user.is_authenticated:
            logger.warning(
                "Platform MCP reached without a resolved platform key "
                f"(org '{org_name}'). Check that this path is not whitelisted."
            )
            return None

        return PlatformMCPContext(
            user=user,
            platform_key=platform_key,
            # Fall back to the key's own organization so the context is never
            # built with a null org, whatever the routing did.
            org_name=org_name or str(platform_key.organization.organization_id),
        )

    def check_tool_allowed(self, tool: Any, context: PlatformMCPContext) -> str | None:
        """Refuse write tools to keys below the read_write tier.

        The middleware's tier check gates on HTTP method, and every MCP call is
        a POST — so it cannot distinguish a tool that reads from one that
        writes. This is where that distinction is actually enforced.

        Today the platform registry is entirely read-only, so this never fires.
        It is here so that adding the first write tool is a one-line change
        that is already guarded, rather than a silent privilege widening.
        """
        if not tool.writes:
            return None

        if context.platform_key.permission == ApiKeyPermission.READ.value:
            return (
                f"Tool '{tool.name}' modifies data and requires a platform API "
                "key with the read_write or full_access permission."
            )
        return None
