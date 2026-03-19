from django.urls import path

from platform_api.views import PlatformApiKeyViewSet

urlpatterns = [
    path(
        "keys/",
        PlatformApiKeyViewSet.as_view({"get": "list", "post": "create"}),
        name="platform_api_key_list",
    ),
    path(
        "keys/<uuid:pk>/",
        PlatformApiKeyViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="platform_api_key_detail",
    ),
    path(
        "keys/<uuid:pk>/rotate/",
        PlatformApiKeyViewSet.as_view({"post": "rotate"}),
        name="platform_api_key_rotate",
    ),
]
