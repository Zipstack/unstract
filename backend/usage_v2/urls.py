from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import UsageView

get_token_usage = UsageView.as_view({"get": "get_token_usage"})
aggregate = UsageView.as_view({"get": UsageView.aggregate.__name__})
usage_list = UsageView.as_view({"get": UsageView.list.__name__})
usage_detail = UsageView.as_view(
    {
        "get": UsageView.retrieve.__name__,
    }
)

# TODO: Refactor URL to avoid using action-specific verbs like get.

urlpatterns = format_suffix_patterns(
    [
        path(
            "get_token_usage/",
            get_token_usage,
            name="get-token-usage",
        ),
        path("", usage_list, name="usage_list"),
        path(
            "aggregate/",
            aggregate,
            name="aggregate",
        ),
        path("<str:pk>/", usage_detail, name="usage_detail"),
    ]
)
