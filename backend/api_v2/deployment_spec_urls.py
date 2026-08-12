"""URLconf used only to generate the API deployment OpenAPI spec.

``api_v2.execution_urls`` is an included sub-urlconf, so generating against it
directly yields paths without the prefix it is mounted at — a spec describing
URLs the server does not serve. This mirrors the mount in ``base_urls``.
"""

from django.conf import settings
from django.urls import include, path

urlpatterns = [
    path(f"{settings.API_DEPLOYMENT_PATH_PREFIX}/", include("api_v2.execution_urls"))
]
