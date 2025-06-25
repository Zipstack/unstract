from django.urls import path

from tags.views import TagViewSet

tag_list = TagViewSet.as_view(
    {
        "get": TagViewSet.list.__name__,
    }
)

tag_detail = TagViewSet.as_view(
    {
        "get": TagViewSet.retrieve.__name__,
    }
)

# Map the custom action for workflow executions
tag_workflow_executions = TagViewSet.as_view(
    {
        "get": TagViewSet.workflow_executions.__name__,
    }
)

tag_workflow_file_executions = TagViewSet.as_view(
    {
        "get": TagViewSet.workflow_file_executions.__name__,
    }
)

urlpatterns = [
    path("", tag_list, name="tag_list"),
    path("<str:pk>/", tag_detail, name="tag_detail"),
    path(
        "<str:pk>/workflow-executions/",
        tag_workflow_executions,
        name="tag_workflow_executions",
    ),
    path(
        "<str:pk>/workflow-file-executions/",
        tag_workflow_file_executions,
        name="tag_workflow_file_executions",
    ),
]
