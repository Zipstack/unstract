from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import prompt_metadata

urlpatterns = format_suffix_patterns(
    [
        path(
            "prompt-metadata/",
            prompt_metadata,
            name="share-manager-metadata",
        ),
    ]
)
