"""Internal API URLs for Organization Context
URL patterns for organization-related internal APIs.
"""

from django.urls import path

from .internal_views import OrganizationContextAPIView

urlpatterns = [
    # Organization context endpoint (backward compatibility)
    path(
        "<str:org_id>/", OrganizationContextAPIView.as_view(), name="organization-context"
    ),
    # Organization context endpoint (explicit path)
    path(
        "<str:org_id>/context/",
        OrganizationContextAPIView.as_view(),
        name="organization-context-explicit",
    ),
]
