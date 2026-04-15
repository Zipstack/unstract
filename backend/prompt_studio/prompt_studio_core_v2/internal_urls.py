"""Internal API URLs for Prompt Studio IDE callbacks."""

from django.urls import path

from . import internal_views

app_name = "prompt_studio_internal"

urlpatterns = [
    path("output/", internal_views.prompt_output, name="prompt-output"),
    path("index/", internal_views.index_update, name="index-update"),
    path("indexing-status/", internal_views.indexing_status, name="indexing-status"),
    path(
        "extraction-status/",
        internal_views.extraction_status,
        name="extraction-status",
    ),
    path(
        "profile/<str:profile_id>/",
        internal_views.profile_detail,
        name="profile-detail",
    ),
    path("hubspot-notify/", internal_views.hubspot_notify, name="hubspot-notify"),
    path(
        "summary-index-key/",
        internal_views.summary_index_key,
        name="summary-index-key",
    ),
]
