from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioOutputView

prompt_doc_list = PromptStudioOutputView.as_view({"get": "list"})
get_output_for_tool_default = PromptStudioOutputView.as_view(
    {"get": "get_output_for_tool_default"}
)

urlpatterns = format_suffix_patterns(
    [
        path("prompt-output/", prompt_doc_list, name="prompt-doc-list"),
        path(
            "prompt-output/prompt-default-profile/",
            get_output_for_tool_default,
            name="prompt-default-profile-outputs",
        ),
    ]
)
