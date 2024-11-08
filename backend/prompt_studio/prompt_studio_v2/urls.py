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

reorder_prompts = ToolStudioPromptView.as_view({"post": "reorder_prompts"})

urlpatterns = format_suffix_patterns(
    [
        path(
            "prompt/<uuid:pk>/",
            prompt_studio_prompt_detail,
            name="tool-studio-prompt-detail",
        ),
        path(
            "prompt/reorder/",
            reorder_prompts,
            name="reorder_prompts",
        ),
    ]
)
