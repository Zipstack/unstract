"""URLconf the published OpenAPI spec is generated against.

Each entry is an included sub-urlconf: generating against one directly yields
paths without the prefix it is mounted at, i.e. a spec describing URLs the
server does not serve. The mounts are selected out of the served urlconf
rather than restated, so moving one moves the generated paths with it.

Widening the spec to another endpoint means annotating its view with
``@extend_schema`` and adding its urlconf here.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import path

from api_v2.api_deployment_views import APIDeploymentViewSet
from backend import base_urls

SPEC_URLCONFS = ("api_v2.execution_urls", "platform_api.whoami_urls")

urlpatterns = [
    entry
    for entry in base_urls.urlpatterns
    if getattr(getattr(entry, "urlconf_name", None), "__name__", None) in SPEC_URLCONFS
]

missing = set(SPEC_URLCONFS) - {entry.urlconf_name.__name__ for entry in urlpatterns}
if missing:
    raise ImproperlyConfigured(
        f"{', '.join(sorted(missing))} is not mounted in backend.base_urls; the "
        "spec would be generated for routes the server does not serve."
    )

# The organisation-scoped listing cannot be selected the way the mounts above
# are: it is served from `api_v2.urls`, which is included several levels deep
# and carries a dozen routes that are not published. So the route is restated
# here, and only for the method that is published --- the same path also serves
# POST to create a deployment, which is not part of this spec.
#
# Both halves of that restatement are drift risks, and `test_docstudio_spec`
# holds them to the served route: the path against `reverse()`, and the method
# against the real URLconf's view.
urlpatterns += [
    path(
        f"{settings.TENANT_SUBFOLDER_PREFIX}/api/deployment/",
        APIDeploymentViewSet.as_view({"get": "list"}),
        name="api_deployment",
    ),
]
