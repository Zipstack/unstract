"""URL patterns for feature_flags app.

This module defines the URL patterns for the feature_flags app.
"""

import feature_flag.views as views
from django.urls import path

urlpatterns = [
    path("evaluate/", views.evaluate_feature_flag, name="evaluate_feature_flag"),
    path("flags/", views.list_feature_flags, name="list_feature_flags"),
]
