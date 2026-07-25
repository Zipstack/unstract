"""URLs for the deployment-scoped MCP server.

Included from ``api_v2/execution_urls.py`` so the MCP endpoint hangs directly
off the deployment's own execution URL — the same resource, reached two ways:

    POST /deployment/api/<org_name>/<api_name>/         (REST)
    POST /deployment/api/<org_name>/<api_name>/mcp      (MCP)

Sitting under ``API_DEPLOYMENT_PATH_PREFIX`` means these paths are already
covered by that prefix's entry in ``WHITELISTED_PATHS``, so
``CustomAuthMiddleware`` skips them and the view authenticates the deployment
key itself — exactly as it does for the execution endpoint next door.
"""

from django.urls import re_path

from mcp_server.views import MCPServerView

mcp_server = MCPServerView.as_view()

urlpatterns = [
    re_path(
        r"^api/(?P<org_name>[\w-]+)/(?P<api_name>[\w-]+)/mcp/?$",
        mcp_server,
        name="mcp_server",
    ),
    # API key as a path segment, for MCP clients that cannot attach an
    # Authorization header to the request. The key is a UUID, so the pattern
    # cannot collide with the header-authenticated route above.
    re_path(
        r"^api/(?P<org_name>[\w-]+)/(?P<api_name>[\w-]+)/mcp/"
        r"(?P<api_key>[0-9a-fA-F-]{36})/?$",
        mcp_server,
        name="mcp_server_with_key",
    ),
]
