from django.urls import path
from prompt_studio.tag_manager.views import TagManagerView
from rest_framework.urlpatterns import format_suffix_patterns

tag_manager_list = TagManagerView.as_view(
    {
        "get": "list",
    }
)
tag_manager_check_in = TagManagerView.as_view(
    {
        "post": "prompt_studio_check_in",
    }
)
tag_manager_load = TagManagerView.as_view(
    {
        "post": "load_checked_in_tag",
    }
)
urlpatterns = format_suffix_patterns(
    [
        path(
            "tag-manager/<uuid:tool_id>/",
            tag_manager_list,
            name="tag-manager-list",
        ),
        path(
            "tag-manager/<uuid:tool_id>/<str:tag>/",
            tag_manager_check_in,
            name="tag-manager-check-in",
        ),
        path(
            "tag-manager/load/<uuid:tool_id>/<str:tag>/",
            tag_manager_load,
            name="tag-manager-check-in",
        ),
    ]
)
