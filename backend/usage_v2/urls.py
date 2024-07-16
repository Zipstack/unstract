from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import UsageView

get_token_usage = UsageView.as_view({"get": "get_token_usage"})

# TODO: Refactor URL to avoid using action-specific verbs like get.

urlpatterns = format_suffix_patterns(
    [
        path(
            "get_token_usage/",
            get_token_usage,
            name="get-token-usage",
        ),
    ]
)
