from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from workflow_manager.workflow_v2.execution_log_view import WorkflowExecutionLogViewSet
from workflow_manager.workflow_v2.execution_view import WorkflowExecutionViewSet
from workflow_manager.workflow_v2.views import WorkflowViewSet

workflow_list = WorkflowViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
workflow_detail = WorkflowViewSet.as_view(
    # fmt: off
    {
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }
    # fmt: on
)
workflow_execute = WorkflowViewSet.as_view({"post": "execute", "put": "activate"})
execution_entity = WorkflowExecutionViewSet.as_view({"get": "retrieve"})
execution_list = WorkflowExecutionViewSet.as_view({"get": "list"})
# execution_log_list = WorkflowExecutionLogViewSet.as_view({"get": "list"})
workflow_clear_cache = WorkflowViewSet.as_view({"get": "clear_cache"})
workflow_clear_file_marker = WorkflowViewSet.as_view({"get": "clear_file_marker"})
workflow_schema = WorkflowViewSet.as_view({"get": "get_schema"})
can_update = WorkflowViewSet.as_view({"get": "can_update"})
urlpatterns = format_suffix_patterns(
    [
        path("", workflow_list, name="workflow-list"),
        path("<uuid:pk>/", workflow_detail, name="workflow-detail"),
        path(
            "<uuid:pk>/clear-cache/",
            workflow_clear_cache,
            name="clear-cache",
        ),
        path(
            "<uuid:pk>/clear-file-marker/",
            workflow_clear_file_marker,
            name="clear-file-marker",
        ),
        path(
            "<uuid:pk>/can-update/",
            can_update,
            name="can-update",
        ),
        path("execute/", workflow_execute, name="execute-workflow"),
        path(
            "active/<uuid:pk>/",
            workflow_execute,
            name="active-workflow",
        ),
        path(
            "<uuid:pk>/execution/",
            execution_list,
            name="execution-list",
        ),
        path(
            "execution/<uuid:pk>/",
            execution_entity,
            name="workflow-detail",
        ),
        # path(
        #     "execution/<uuid:pk>/logs/",
        #     execution_log_list,
        #     name="execution-log",
        # ),
        path(
            "schema/",
            workflow_schema,
            name="workflow-schema",
        ),
    ]
)
