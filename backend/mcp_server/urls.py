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
]

# There is deliberately no route carrying the API key as a path segment. An
# earlier revision offered one for "MCP clients that cannot set headers", but
# that client class does not exist for HTTP transports: the spec requires
# `Authorization` on every authenticated request ("Authorization MUST be
# included in every HTTP request from client to server"), and states that
# access tokens MUST NOT appear in the URI. A key in the path reaches nginx and
# gunicorn access logs, APM traces, and any intermediary — places a header
# never goes — and rotating a deployment key is not free.
#
# Basic auth would be spec-legal and is supported by MCP clients, but buys
# nothing here: it is the same `Authorization` header as Bearer, and base64 is
# encoding rather than encryption. Any client that can send one can send both.
