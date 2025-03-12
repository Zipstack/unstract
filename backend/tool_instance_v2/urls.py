from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns
from tool_instance_v2.views import ToolInstanceViewSet

from . import views

tool_instance_list = ToolInstanceViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)
tool_instance_detail = ToolInstanceViewSet.as_view(
    # fmt: off
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy"
    }
    # fmt: on
)

tool_instance_reorder = ToolInstanceViewSet.as_view({"post": "reorder"})

urlpatterns = format_suffix_patterns(
    [
        path("tool_instance/", tool_instance_list, name="tool-instance-list"),
        path(
            "tool_instance/<uuid:pk>/",
            tool_instance_detail,
            name="tool-instance-detail",
        ),
        path(
            "tool_settings_schema/",
            views.tool_settings_schema,
            name="tool_settings_schema",
        ),
        path(
            "tool_instance/reorder/",
            tool_instance_reorder,
            name="tool_instance_reorder",
        ),
        path("tool/", views.get_tool_list, name="tool_list"),
        path(
            "tool/prompt-studio/",
            views.get_prompt_studio_tool_count,
            name="prompt_studio_tool_count",
        ),
    ]
)
