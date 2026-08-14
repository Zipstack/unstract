from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptStudioRegistryView

urlpatterns = [
    path(
        "registry/",
        PromptStudioRegistryView.as_view({"get": "list"}),
        name="prompt_studio_registry_list",
    ),
    path(
        "registry/<uuid:pk>/",
        PromptStudioRegistryView.as_view({"delete": "destroy"}),
        name="prompt_studio_registry_detail",
    ),
]

# Optional: Apply format suffix patterns
urlpatterns = format_suffix_patterns(urlpatterns)
