from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioRegistryView

tool_studio_export = PromptStudioRegistryView.as_view({"get": "export_tool"})
urlpatterns = format_suffix_patterns(
    [
        path(
            "export/",
            tool_studio_export,
            name="prompt_studio_export",
        ),
    ]
)
