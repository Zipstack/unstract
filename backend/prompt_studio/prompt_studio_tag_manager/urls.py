from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ToolStudioPromptTagView

prompt_studio_prompt_detail = ToolStudioPromptTagView.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "prompt_tag/<uuid:pk>/",
            prompt_studio_prompt_detail,
            name="tool-studio-prompt-tags",
        ),
    ]
)
