from django.urls import path

from connector_processor.views import ConnectorViewSet

connector_test = ConnectorViewSet.as_view({"post": "test"})
connector_schema = ConnectorViewSet.as_view({"get": "connector_schema"})
supported_connectors = ConnectorViewSet.as_view({"get": "supported_connectors"})

urlpatterns = [
    path(
        "connector_schema/",
        connector_schema,
        name="get_connector_schema",
    ),
    path(
        "supported_connectors/",
        supported_connectors,
        name="get_supported_connectors",
    ),
    path("test_connectors/", connector_test, name="connector-test"),
]
