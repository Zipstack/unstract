from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import SPSPromptOutputView

sps_prompt_output = SPSPromptOutputView.as_view({"get": "list"})

urlpatterns = format_suffix_patterns(
    [
        path("prompt-output", sps_prompt_output, name="spsprompt-output"),
    ]
)
