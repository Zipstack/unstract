"""Internal API URLs for file history operations."""

from django.urls import path

from .views import (
    create_file_history_internal,
    file_history_batch_lookup_internal,
    file_history_by_cache_key_internal,
    file_history_status_internal,
    get_file_history_internal,
    reserve_file_processing_internal,
)

urlpatterns = [
    # File history endpoints
    path(
        "cache-key/<str:cache_key>/",
        file_history_by_cache_key_internal,
        name="file-history-by-cache-key-internal",
    ),
    # Flexible lookup endpoint (supports both cache_key and provider_file_uuid)
    path(
        "lookup/",
        file_history_by_cache_key_internal,
        name="file-history-lookup-internal",
    ),
    # Batch lookup endpoint for multiple files
    path(
        "batch-lookup/",
        file_history_batch_lookup_internal,
        name="file-history-batch-lookup-internal",
    ),
    path("create/", create_file_history_internal, name="create-file-history-internal"),
    path(
        "status/<str:file_history_id>/",
        file_history_status_internal,
        name="file-history-status-internal",
    ),
    path(
        "reserve/",
        reserve_file_processing_internal,
        name="reserve-file-processing-internal",
    ),
    path("get/", get_file_history_internal, name="get-file-history-internal"),
]
