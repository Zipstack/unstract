from django.urls import include, re_path
from rest_framework.urlpatterns import format_suffix_patterns

from api_v2.api_deployment_views import DeploymentExecution

execute = DeploymentExecution.as_view()


# The deployment MCP server hangs off the execution URL
# (``…/<api_name>/mcp``), so it is matched first. The execution pattern below
# anchors with ``$`` and cannot swallow the ``/mcp`` suffix on its own, but
# ordering it first keeps that independent of the other pattern's exact shape.
# Kept outside ``format_suffix_patterns`` because that helper rewrites leaf
# patterns and is not meant to wrap an ``include()``.
urlpatterns = [re_path(r"^", include("mcp_server.urls"))]

urlpatterns += format_suffix_patterns(
    [
        re_path(
            r"^api/(?P<org_name>[\w-]+)/(?P<api_name>[\w-]+)/?$",
            execute,
            name="api_deployment_execution",
        )
    ]
)
