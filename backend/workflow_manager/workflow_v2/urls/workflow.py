from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from workflow_manager.workflow_v2.execution_log_view import WorkflowExecutionLogViewSet
from workflow_manager.workflow_v2.execution_view import WorkflowExecutionViewSet
from workflow_manager.workflow_v2.file_history_views import FileHistoryViewSet
from workflow_manager.workflow_v2.views import WorkflowViewSet

workflow_list = WorkflowViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
workflow_detail = WorkflowViewSet.as_view(
    # fmt: off
    {"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"}
    # fmt: on
)
workflow_execute = WorkflowViewSet.as_view({"post": "execute", "put": "activate"})
execution_entity = WorkflowExecutionViewSet.as_view({"get": "retrieve"})
execution_list = WorkflowExecutionViewSet.as_view({"get": "list"})
execution_log_list = WorkflowExecutionLogViewSet.as_view({"get": "list"})
workflow_clear_file_marker = WorkflowViewSet.as_view({"get": "clear_file_marker"})
workflow_schema = WorkflowViewSet.as_view({"get": "get_schema"})
can_update = WorkflowViewSet.as_view({"get": "can_update"})
list_shared_users = WorkflowViewSet.as_view({"get": "list_of_shared_users"})
workflow_add_owner = WorkflowViewSet.as_view({"post": "add_co_owner"})
workflow_remove_owner = WorkflowViewSet.as_view({"delete": "remove_co_owner"})

# File History views
file_history_list = FileHistoryViewSet.as_view({"get": "list"})
file_history_detail = FileHistoryViewSet.as_view({"get": "retrieve", "delete": "destroy"})
file_history_clear = FileHistoryViewSet.as_view({"post": "clear"})

urlpatterns = format_suffix_patterns(
    [
        path("", workflow_list, name="workflow-list"),
        path("<uuid:pk>/", workflow_detail, name="workflow-detail"),
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
        path(
            "<uuid:pk>/users/",
            list_shared_users,
            name="list-shared-users",
        ),
        path(
            "<uuid:pk>/owners/",
            workflow_add_owner,
            name="workflow-add-owner",
        ),
        path(
            "<uuid:pk>/owners/<int:user_id>/",
            workflow_remove_owner,
            name="workflow-remove-owner",
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
        path(
            "execution/<uuid:pk>/logs/",
            execution_log_list,
            name="execution-log",
        ),
        path(
            "schema/",
            workflow_schema,
            name="workflow-schema",
        ),
        # File History nested routes
        path(
            "<uuid:workflow_id>/file-histories/",
            file_history_list,
            name="workflow-file-history-list",
        ),
        path(
            "<uuid:workflow_id>/file-histories/<uuid:id>/",
            file_history_detail,
            name="workflow-file-history-detail",
        ),
        path(
            "<uuid:workflow_id>/file-histories/clear/",
            file_history_clear,
            name="workflow-file-history-clear",
        ),
    ]
)
