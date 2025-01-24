# base_urls.py
from django.conf import settings
from django.urls import include, path

from .public_urls_v2 import urlpatterns as public_urls

# Import urlpatterns from each file
from .urls_v2 import urlpatterns as tenant_urls

# Combine the URL patterns
urlpatterns = [
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
]
