"""URLconf used only to generate the API deployment OpenAPI spec.

``api_v2.execution_urls`` is an included sub-urlconf, so generating against it
directly yields paths without the prefix it is mounted at — a spec describing
URLs the server does not serve. The mount is selected out of the served
urlconf rather than restated here, so a change to where the deployment API is
mounted moves the generated paths with it.
"""

from django.core.exceptions import ImproperlyConfigured

from backend import base_urls

DEPLOYMENT_URLCONF = "api_v2.execution_urls"

urlpatterns = [
    entry
    for entry in base_urls.urlpatterns
    if getattr(getattr(entry, "urlconf_name", None), "__name__", None)
    == DEPLOYMENT_URLCONF
]

if not urlpatterns:
    raise ImproperlyConfigured(
        f"{DEPLOYMENT_URLCONF} is not mounted in backend.base_urls; the API "
        "deployment spec would be generated for no routes at all."
    )
