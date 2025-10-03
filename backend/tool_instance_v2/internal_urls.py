"""Internal API URLs for tool instance operations."""

from django.urls import path

from .internal_views import tool_by_id_internal, validate_tool_instances_internal

urlpatterns = [
    # Tool by ID endpoint - critical for worker functionality
    path("tool/<str:tool_id>/", tool_by_id_internal, name="tool-by-id-internal"),
    # Tool instance validation endpoint - used by workers before execution
    path(
        "validate/",
        validate_tool_instances_internal,
        name="validate-tool-instances-internal",
    ),
]
