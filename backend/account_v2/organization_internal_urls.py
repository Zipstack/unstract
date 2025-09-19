"""Account Internal API URLs
Defines internal API endpoints for organization operations.
"""

from django.urls import path

from .internal_views import OrganizationContextAPIView

urlpatterns = [
    # Organization context API
    path(
        "<str:org_id>/context/",
        OrganizationContextAPIView.as_view(),
        name="organization-context",
    ),
]
