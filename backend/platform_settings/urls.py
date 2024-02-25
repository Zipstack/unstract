from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PlatformKeyViewSet

platform_key_list = PlatformKeyViewSet.as_view(
    {"post": "create", "put": "refresh", "get": "list"}
)
platform_key_update = PlatformKeyViewSet.as_view(
    {"put": "toggle_platform_key", "delete": "destroy"}
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
    ]
)
