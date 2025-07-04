"""URL patterns for feature_flags app.

This module defines the URL patterns for the feature_flags app.
"""

from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from feature_flag.views import FeatureFlagViewSet

feature_flags_list = FeatureFlagViewSet.as_view(
    {
        "post": "evaluate",
        "get": "list",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("evaluate/", feature_flags_list, name="evaluate_feature_flag"),
        path("flags/", feature_flags_list, name="list_feature_flags"),
    ]
)
