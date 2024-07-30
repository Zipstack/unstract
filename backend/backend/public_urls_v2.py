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

from account_v2.admin import admin
from django.conf import settings
from django.conf.urls import *  # noqa: F401, F403
from django.conf.urls.static import static
from django.urls import include, path

path_prefix = settings.PATH_PREFIX
api_path_prefix = settings.API_DEPLOYMENT_PATH_PREFIX

urlpatterns = [
    path("", include("account_v2.urls")),
    # Connector OAuth
    path("", include("connector_auth_v2.urls")),
    # # Docs
    path("", include("docs.urls")),
    # # # API deployment
    # path("api/", include("api_v2.execution_urls")),
    # # Feature flags
    path("flags/", include("feature_flag.urls")),
]
if settings.ADMIN_ENABLED:
    # Admin URLs
    urlpatterns += [
        path("admin/", admin.site.urls),
        path(
            "admin/doc/",
            include("django.contrib.admindocs.urls"),
        ),
    ]
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


try:
    import pluggable_apps.platform_admin.urls  # noqa: F401

    urlpatterns += [
        path("", include("pluggable_apps.platform_admin.urls")),
    ]
except ImportError:
    pass
