from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ShareViewSet

# prompt_studio_prompt_response = ShareViewSet.as_view({"post": "fetch_response"})

share_list = ShareViewSet.as_view({"get": "list", "post": "create"})
share_detail = ShareViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)


urlpatterns = format_suffix_patterns(
    [
        path("share-manager/", share_list, name="share-list"),
        path("share-manager/<uuid:pk>/", share_detail, name="share-detail"),
    ]
)
