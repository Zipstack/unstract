"""Internal API URLs for API v2

Internal endpoints for worker communication, specifically optimized
for type-aware pipeline data fetching.
"""

from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from api_v2.internal_api_views import APIDeploymentDataView

urlpatterns = format_suffix_patterns(
    [
        path(
            "<uuid:api_id>/",
            APIDeploymentDataView.as_view(),
            name="api_deployment_data_internal",
        ),
    ]
)
