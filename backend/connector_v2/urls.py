from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ConnectorInstanceViewSet as CIViewSet, SharedConnectorViewSet

connector_list = CIViewSet.as_view({"get": "list", "post": "create"})
connector_detail = CIViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

# Shared connector endpoints
shared_connector_list = SharedConnectorViewSet.as_view({"get": "list", "post": "create"})
shared_connector_detail = SharedConnectorViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)
shared_connector_test = SharedConnectorViewSet.as_view({"post": "test_connection"})
shared_connector_by_type = SharedConnectorViewSet.as_view({"get": "by_type"})

urlpatterns = format_suffix_patterns(
    [
        # Legacy workflow-specific connectors (keep for backwards compatibility)
        path("connector/", connector_list, name="connector-list"),
        path("connector/<uuid:pk>/", connector_detail, name="connector-detail"),
        
        # New shared/centralized connectors
        path("shared-connectors/", shared_connector_list, name="shared-connector-list"),
        path("shared-connectors/<uuid:pk>/", shared_connector_detail, name="shared-connector-detail"),
        path("shared-connectors/<uuid:pk>/test/", shared_connector_test, name="shared-connector-test"),
        path("shared-connectors/by-type/", shared_connector_by_type, name="shared-connector-by-type"),
    ]
)
