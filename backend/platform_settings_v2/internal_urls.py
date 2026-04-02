"""Internal URLs for platform settings

Routes for internal API endpoints used by workers.
"""

from django.urls import path

from .internal_views import InternalPlatformKeyView

app_name = "platform_settings_internal"

urlpatterns = [
    path(
        "platform-key/",
        InternalPlatformKeyView.as_view(),
        name="platform_key",
    ),
]
