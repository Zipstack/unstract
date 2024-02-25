from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from workflow_manager.workflow.views import WorkflowViewSet

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
workflow_execute = WorkflowViewSet.as_view(
    {"post": "execute", "put": "activate"}
)
execution_entity = WorkflowViewSet.as_view({"get": "get_execution"})
workflow_clear_cache = WorkflowViewSet.as_view({"get": "clear_cache"})
workflow_clear_file_marker = WorkflowViewSet.as_view(
    {"get": "clear_file_marker"}
)
workflow_schema = WorkflowViewSet.as_view({"get": "get_schema"})
workflow_settings = WorkflowViewSet.as_view(
    {"get": "workflow_settings", "put": "workflow_settings"}
)
workflow_settings_schema = WorkflowViewSet.as_view(
    {"get": "workflow_settings_schema"}
)

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
        path("execute/", workflow_execute, name="execute-workflow"),
        path(
            "active/<uuid:pk>/",
            workflow_execute,
            name="active-workflow",
        ),
        path(
            "execution/<uuid:pk>/",
            execution_entity,
            name="workflow-detail",
        ),
        path(
            "schema/",
            workflow_schema,
            name="workflow-schema",
        ),
        path(
            "<uuid:pk>/settings/", workflow_settings, name="workflow-settings"
        ),
        path(
            "settings/",
            workflow_settings_schema,
            name="workflow-settings-schema",
        ),
    ]
)
