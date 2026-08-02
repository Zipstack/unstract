"""URLs for the organization-scoped MCP server.

Mounted under the tenant prefix in ``backend/urls_v2.py``, alongside
``platform-api/``:

    POST /api/v1/unstract/<org_name>/mcp/

That placement is load-bearing, and the reason is the *prefix*, not the
``/mcp`` segment. ``WHITELISTED_PATHS`` is matched with ``startswith`` and
contains ``/{API_DEPLOYMENT_PATH_PREFIX}`` — i.e. ``/deployment`` — so the
deployment MCP server is exempt from ``CustomAuthMiddleware`` because it hangs
off ``/deployment/api/...``, and authenticates its own key instead. Nothing in
that list mentions ``/mcp``.

This path starts with ``/api/v1/unstract/`` and so matches no whitelist entry,
which is precisely how it inherits platform-key authentication for free.
Re-mounting it under ``/deployment/`` would silently remove all authentication.
"""

from django.urls import path

from mcp_server.platform_views import PlatformMCPServerView

urlpatterns = [
    path("", PlatformMCPServerView.as_view(), name="platform_mcp_server"),
]
