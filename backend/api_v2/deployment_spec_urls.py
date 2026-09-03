"""URLconf the published OpenAPI spec is generated against.

Each entry is an included sub-urlconf: generating against one directly yields
paths without the prefix it is mounted at, i.e. a spec describing URLs the
server does not serve. The mounts are selected out of the served urlconf
rather than restated, so moving one moves the generated paths with it.

Widening the spec to another endpoint means annotating its view with
``@extend_schema`` and adding its urlconf here.
"""

from django.core.exceptions import ImproperlyConfigured

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
