"""URLs for the organization-scoped MCP server.

Mounted under the tenant prefix in ``backend/urls_v2.py``, alongside
``platform-api/``:

    POST /api/v1/unstract/<org_name>/mcp/

That placement is load-bearing. ``WHITELISTED_PATHS`` is matched with
``startswith``, so the deployment server's ``/mcp/...`` is exempt from
``CustomAuthMiddleware`` while this path is not — which is precisely how this
server inherits platform-key authentication for free. Moving these URLs under
the whitelisted prefix would silently remove all authentication.
"""

from django.urls import path

from mcp_server.platform_views import PlatformMCPServerView

urlpatterns = [
    path("", PlatformMCPServerView.as_view(), name="platform_mcp_server"),
]
