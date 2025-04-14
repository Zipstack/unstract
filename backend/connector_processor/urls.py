from django.urls import path

from connector_processor.views import ConnectorViewSet

from . import views

connector_test = ConnectorViewSet.as_view({"post": "test"})

urlpatterns = [
    path(
        "connector_schema/",
        views.get_connector_schema,
        name="get_connector_schema",
    ),
    path(
        "supported_connectors/",
        views.get_supported_connectors,
        name="get_supported_connectors",
    ),
    path("test_connectors/", connector_test, name="connector-test"),
]
