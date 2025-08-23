"""Internal API URLs for tool instance operations."""

from django.urls import path

from .views import tool_by_id_internal

urlpatterns = [
    # Tool by ID endpoint - critical for worker functionality
    path("tool/<str:tool_id>/", tool_by_id_internal, name="tool-by-id-internal"),
]
