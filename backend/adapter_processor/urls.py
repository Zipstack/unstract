from adapter_processor.views import (
    AdapterInstanceViewSet,
    AdapterViewSet,
    DefaultAdapterViewSet,
)
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

default_triad = DefaultAdapterViewSet.as_view(
    {"post": "configure_default_triad"}
)
adapter = AdapterViewSet.as_view({"get": "list"})
adapter_schema = AdapterViewSet.as_view({"get": "get_adapter_schema"})
adapter_test = AdapterViewSet.as_view({"post": "test"})
adapter_list = AdapterInstanceViewSet.as_view({"post": "create", "get": "list"})
adapter_detail = AdapterInstanceViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)
urlpatterns = format_suffix_patterns(
    [
        path("adapter_schema/", adapter_schema, name="get_adapter_schema"),
        path("supported_adapters/", adapter, name="adapter-list"),
        path("adapter/", adapter_list, name="adapter-list"),
        path("adapter/default_triad/", default_triad, name="default_triad"),
        path("adapter/<uuid:pk>/", adapter_detail, name="adapter_detail"),
        path("test_adapters/", adapter_test, name="adapter-test"),
    ]
)
