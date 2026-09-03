# base_urls.py
from django.conf import settings
from django.urls import include, path

from .public_urls_v2 import urlpatterns as public_urls

# Import urlpatterns from each file
from .urls_v2 import urlpatterns as tenant_urls

# Combine the URL patterns
urlpatterns = [
    # Organisation-less, and so mounted ahead of the tenant urlconf rather than
    # relying on falling through it. Nothing is shadowed today because no tenant
    # urlconf declares `whoami/`; mounting first is what makes this route win if
    # one ever does.
    #
    # Note this is not the only URL that reaches the view. `OrganizationMiddleware`
    # strips the organisation segment before routing, so
    # `/api/v1/unstract/<org>/whoami/` is rewritten to exactly this path and
    # resolves here too -- with `organization_id` set, so the key-belongs-to-org
    # check in `CustomAuthMiddleware` additionally applies. That alias is
    # stricter, not looser; `test_whoami.py` covers both forms.
    path(
        f"{settings.TENANT_SUBFOLDER_PREFIX}/",
        include("platform_api.whoami_urls"),
    ),
    path(
        f"{settings.TENANT_SUBFOLDER_PREFIX}/",
        include((tenant_urls, "tenant"), namespace="tenant"),
    ),
    path(
        f"{settings.PATH_PREFIX}/", include((public_urls, "public"), namespace="public")
    ),
    # API deployment
    path(f"{settings.API_DEPLOYMENT_PATH_PREFIX}/", include("api_v2.execution_urls")),
    path(
        f"{settings.API_DEPLOYMENT_PATH_PREFIX}/pipeline/",
        include("pipeline_v2.public_api_urls"),
    ),
    path("", include("health.urls")),
    # Internal API for worker communication
    path("internal/", include("backend.internal_base_urls")),
]
