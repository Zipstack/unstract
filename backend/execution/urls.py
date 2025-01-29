from django.urls import path
from execution.views import ExecutionViewSet
from rest_framework.urlpatterns import format_suffix_patterns

execution_list = ExecutionViewSet.as_view(
    {
        "get": "list",
    }
)
execution_detail = ExecutionViewSet.as_view({"get": "retrieve", "delete": "destroy"})

urlpatterns = format_suffix_patterns(
    [
        path("", execution_list, name="execution-list"),
        path("<uuid:pk>/", execution_detail, name="execution-detail"),
    ]
)
