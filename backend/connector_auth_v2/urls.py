from django.urls import include, path, re_path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ConnectorAuthViewSet

connector_auth_cache = ConnectorAuthViewSet.as_view(
    {
        "get": "cache_key",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("oauth/", include("social_django.urls", namespace="social")),
        re_path(
            "^oauth/cache-key/(?P<backend>.+)$",
            connector_auth_cache,
            name="connector-cache",
        ),
    ]
)
