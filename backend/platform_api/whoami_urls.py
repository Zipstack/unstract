"""The organisation-less ``whoami`` route.

Kept apart from ``platform_api.urls`` because it is mounted directly on the
tenant prefix rather than under ``platform-api/``, and because the OpenAPI
spec's urlconf selector can only pick out a mount declared with a dotted
module path (see ``api_v2.deployment_spec_urls``).
"""

from django.urls import path

from platform_api.whoami_views import WhoAmIView

urlpatterns = [
    path("whoami/", WhoAmIView.as_view(), name="platform_whoami"),
]
