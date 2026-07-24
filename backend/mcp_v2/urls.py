"""URLs for the hosted MCP server.

Mounted alongside the API deployment execution endpoint so an MCP endpoint is
the same shape as the REST endpoint for the same deployment:

    POST /deployment/api/<org_name>/<api_name>/     (REST)
    POST /mcp/<org_name>/<api_name>/                (MCP)
"""

from django.urls import re_path

from mcp_v2.views import MCPServerView

mcp_server = MCPServerView.as_view()

urlpatterns = [
    re_path(
        r"^(?P<org_name>[\w-]+)/(?P<api_name>[\w-]+)/?$",
        mcp_server,
        name="mcp_server",
    ),
    # API key as a path segment, for MCP clients that cannot attach an
    # Authorization header to the request. The key is a UUID, so the pattern
    # cannot collide with the header-authenticated route above.
    re_path(
        r"^(?P<org_name>[\w-]+)/(?P<api_name>[\w-]+)/"
        r"(?P<api_key>[0-9a-fA-F-]{36})/?$",
        mcp_server,
        name="mcp_server_with_key",
    ),
]
