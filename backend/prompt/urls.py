from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import PromptViewSet

prompt_list = PromptViewSet.as_view({"get": "list", "post": "create"})
prompt_detail = PromptViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("prompt/", prompt_list, name="prompt-list"),
        path("prompt/<uuid:pk>/", prompt_detail, name="prompt-detail"),
    ]
)
