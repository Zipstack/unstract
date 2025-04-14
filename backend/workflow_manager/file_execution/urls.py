from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from workflow_manager.file_execution.views import FileCentricExecutionViewSet

file_centric_list = FileCentricExecutionViewSet.as_view({"get": "list"})

urlpatterns = format_suffix_patterns(
    [
        path("<uuid:pk>/files/", file_centric_list, name="file-centric-execution-list"),
    ]
)
