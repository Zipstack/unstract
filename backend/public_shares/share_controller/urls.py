from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import (
    document_manager,
    get_select_choices,
    profile_manager,
    prompt_manager,
    prompt_metadata,
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "share/prompt-metadata/",
            prompt_metadata,
            name="share-manager-metadata",
        ),
        path(
            "share/select-choices/",
            get_select_choices,
            name="share-manager-choices",
        ),
        path(
            "share/document-metadata/",
            document_manager,
            name="share-manager-document",
        ),
        path(
            "share/profiles-metadata/",
            profile_manager,
            name="share-manager-profile",
        ),
        path(
            "share/prompts-metadata/",
            prompt_manager,
            name="share-manager-prompt",
        ),
    ]
)
