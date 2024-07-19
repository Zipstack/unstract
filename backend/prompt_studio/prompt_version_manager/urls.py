from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptVersionManagerView

prompt_version_manager_actions = PromptVersionManagerView.as_view(
    {
        "get": "list",
        "post": "load_version",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "prompt-version-manager/<uuid:prompt_id>/",
            prompt_version_manager_actions,
            name="prompt_version_manager_actions",
        ),
    ]
)
