from django.urls import path
from workflow_manager.endpoint_v2.views import WorkflowEndpointViewSet

workflow_endpoint_list = WorkflowEndpointViewSet.as_view(
    {"get": "workflow_endpoint_list"}
)
endpoint_list = WorkflowEndpointViewSet.as_view({"get": "list"})
workflow_endpoint_detail = WorkflowEndpointViewSet.as_view(
    {"get": "retrieve", "put": "update"}
)
endpoint_settings_detail = WorkflowEndpointViewSet.as_view(
    {"get": WorkflowEndpointViewSet.get_settings.__name__}
)

urlpatterns = [
    path("", endpoint_list, name="endpoint-list"),
    path("<str:pk>/", workflow_endpoint_detail, name="workflow-endpoint-detail"),
    path(
        "<str:pk>/settings/",
        endpoint_settings_detail,
        name="workflow-endpoint-detail",
    ),
]
