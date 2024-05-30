from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ShareViewSet

# prompt_studio_prompt_response = ShareViewSet.as_view({"post": "fetch_response"})

share_detail = ShareViewSet.as_view({"get": "list", "post": "create"})


urlpatterns = format_suffix_patterns(
    [
        path("share-manager/", share_detail, name="share-detail"),
    ]
)
