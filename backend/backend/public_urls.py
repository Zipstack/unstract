"""URL configuration for backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from account.admin import admin
from django.conf import settings
from django.conf.urls import *  # noqa: F401, F403
from django.conf.urls.static import static
from django.urls import include, path

path_prefix = settings.PATH_PREFIX
api_path_prefix = settings.API_DEPLOYMENT_PATH_PREFIX

urlpatterns = [
    path(f"{path_prefix}/", include("account.urls")),
    # Connector OAuth
    path(f"{path_prefix}/", include("connector_auth.urls")),
    # Docs
    path(f"{path_prefix}/", include("docs.urls")),
    # API deployment
    path(f"{api_path_prefix}/", include("api.urls")),
    # Feature flags
    path(f"{path_prefix}/flags/", include("feature_flag.urls")),
]
if settings.ADMIN_ENABLED:
    # Admin URLs
    urlpatterns += [
        path(f"{path_prefix}/admin/", admin.site.urls),
        path(
            f"{path_prefix}/admin/doc/",
            include("django.contrib.admindocs.urls"),
        ),
    ]
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

try:
    import pluggable_apps.platform_admin.urls  # noqa # pylint: disable=unused-import

    urlpatterns += [
        path(f"{path_prefix}/", include("pluggable_apps.platform_admin.urls")),
    ]
except ImportError:
    pass

try:
    import pluggable_apps.public_shares.share_controller.urls  # noqa # pylint: disable=unused-import

    share_path_prefix = settings.PUBLIC_PATH_PREFIX

    urlpatterns += [
        # Public Sharing
        path(
            f"{share_path_prefix}/",
            include("pluggable_apps.public_shares.share_controller.urls"),
        ),
    ]
except ImportError:
    pass

try:
    mr_path_prefix = settings.MANUAL_REVEIEW_QUEUE_PATH_PREFIX
    import pluggable_apps.manual_review.public_urls  # noqa # pylint: disable=unused-import

    urlpatterns += [
        path(f"{mr_path_prefix}/", include("pluggable_apps.manual_review.public_urls")),
    ]
except ImportError:
    pass
