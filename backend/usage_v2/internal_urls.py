"""Internal API URLs for Usage access by workers."""

from django.urls import path

from . import internal_views

app_name = "usage_internal"

urlpatterns = [
    path(
        "aggregated-token-count/<str:file_execution_id>/",
        internal_views.UsageInternalView.as_view(),
        name="aggregated-token-count",
    ),
    path(
        "aggregated-pages-processed/<str:file_execution_id>/",
        internal_views.PagesProcessedInternalView.as_view(),
        name="aggregated-pages-processed",
    ),
]
