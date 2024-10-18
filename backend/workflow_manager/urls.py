from django.urls import include, path
from workflow_manager.endpoint_v2 import urls as endpoint_urls
from workflow_manager.workflow_v2 import urls as workflow_urls

urlpatterns = [
    path("endpoint/", include(endpoint_urls)),
    path(
        "<uuid:pk>/endpoint/",
        include(
            [
                path(
                    "",
                    endpoint_urls.workflow_endpoint_list,
                    name="workflow-endpoint",
                )
            ]
        ),
    ),
    path("", include(workflow_urls)),
]
