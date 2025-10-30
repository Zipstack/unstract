from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PlatformKeyViewSet, PlatformSettingsViewSet

platform_key_list = PlatformKeyViewSet.as_view(
    {"post": "create", "put": "refresh", "get": "list"}
)
platform_key_update = PlatformKeyViewSet.as_view(
    {"put": "toggle_platform_key", "delete": "destroy"}
)

platform_settings_view = PlatformSettingsViewSet.as_view(
    {"get": "list", "put": "update", "patch": "update"}
)

platform_settings_system_llm = PlatformSettingsViewSet.as_view(
    {"get": "system_llm"}
)

urlpatterns = format_suffix_patterns(
    [
        path(
            "keys/",
            platform_key_list,
            name="generate_platform_key",
        ),
        path(
            "keys/<uuid:pk>/",
            platform_key_update,
            name="update_platform_key",
        ),
        path(
            "settings/",
            platform_settings_view,
            name="platform_settings",
        ),
        path(
            "settings/system-llm/",
            platform_settings_system_llm,
            name="platform_settings_system_llm",
        ),
    ]
)
