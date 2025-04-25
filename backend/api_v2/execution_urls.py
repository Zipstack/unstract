from django.urls import re_path
from rest_framework.urlpatterns import format_suffix_patterns

from api_v2.api_deployment_views import DeploymentExecution

execute = DeploymentExecution.as_view()


urlpatterns = format_suffix_patterns(
    [
        re_path(
            r"^api/(?P<org_name>[\w-]+)/(?P<api_name>[\w-]+)/?$",
            execute,
            name="api_deployment_execution",
        )
    ]
)
