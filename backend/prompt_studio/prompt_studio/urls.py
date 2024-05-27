from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ToolStudioPromptView

prompt_studio_prompt_detail = ToolStudioPromptView.as_view(
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
            "prompt/<uuid:pk>/",
            prompt_studio_prompt_detail,
            name="tool-studio-prompt-detail",
        ),
    ]
)
