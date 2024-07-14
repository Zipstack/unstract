from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptVersionManagerView

prompt_version_manager_list = PromptVersionManagerView.as_view(
    {
        "get": "list",
    }
)
prompt_version_manager_load = PromptVersionManagerView.as_view(
    {
        "post": "load_version",
    }
)
urlpatterns = format_suffix_patterns(
    [
        path(
            "prompt-version-manager/<uuid:prompt_id>/",
            prompt_version_manager_list,
            name="prompt-version-manager-list",
        ),
        path(
            "prompt-version-manager/<uuid:prompt_id>/<str:prompt_version>",
            prompt_version_manager_load,
            name="prompt-version-manager-list",
        ),
    ]
)
