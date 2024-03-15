from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioCoreView

prompt_studio_list = PromptStudioCoreView.as_view(
    {"get": "list", "post": "create"}
)
prompt_studio_detail = PromptStudioCoreView.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)
prompt_studio_choices = PromptStudioCoreView.as_view(
    {"get": "get_select_choices"}
)
prompt_studio_profiles = PromptStudioCoreView.as_view(
    {"get": "list_profiles", "patch": "make_profile_default"}
)

prompt_studio_prompt_index = PromptStudioCoreView.as_view(
    {"post": "index_document"}
)
prompt_studio_prompt_response = PromptStudioCoreView.as_view(
    {"post": "fetch_response"}
)
prompt_studio_adapter_choices = PromptStudioCoreView.as_view(
    {"get": "get_adapter_choices"}
)
prompt_studio_single_pass_extraction = PromptStudioCoreView.as_view(
    {"post": "single_pass_extraction"}
)

urlpatterns = format_suffix_patterns(
    [
        path("prompt-studio/", prompt_studio_list, name="prompt-studio-list"),
        path(
            "prompt-studio/<uuid:pk>/",
            prompt_studio_detail,
            name="tool-studio-detail",
        ),
        path(
            "prompt-studio/select_choices/",
            prompt_studio_choices,
            name="prompt-studio-choices",
        ),
        path(
            "prompt-studio/profiles/<uuid:pk>/",
            prompt_studio_profiles,
            name="prompt-studio-profiles",
        ),
        path(
            "prompt-studio/index-document/",
            prompt_studio_prompt_index,
            name="prompt-studio-prompt-index",
        ),
        path(
            "prompt-studio/fetch_response/",
            prompt_studio_prompt_response,
            name="prompt-studio-prompt-response",
        ),
        path(
            "prompt-studio/adapter-choices/",
            prompt_studio_adapter_choices,
            name="prompt-studio-adapter-choices",
        ),
        path(
            "prompt-studio/single-pass-extraction",
            prompt_studio_single_pass_extraction,
            name="prompt-studio-single-pass-extraction",
        ),
    ]
)
