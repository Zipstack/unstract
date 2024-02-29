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
from django.urls import include, path

path_prefix = settings.PATH_PREFIX
api_path_prefix = settings.API_DEPLOYMENT_PATH_PREFIX
internal_path_prefix = settings.INTERNAL_PATH_PREFIX

urlpatterns = [
    path(f"{path_prefix}/", include("account.urls")),
    # Admin URLs
    path(f"{path_prefix}/admin/doc/", include("django.contrib.admindocs.urls")),
    path(f"{path_prefix}/admin/", admin.site.urls),
    # Connector OAuth
    path(f"{path_prefix}/", include("connector_auth.urls")),
    # Docs
    path(f"{path_prefix}/", include("docs.urls")),
    # Socket.io
    path(f"{path_prefix}/", include("log_events.urls")),
    # API deployment
    path(f"{api_path_prefix}/", include("api.urls")),
    # Feature flags
    path(f"{path_prefix}/flags/", include("feature_flag.urls")),
    # To load details of an app deployment
    path(
        f"{path_prefix}/apps/",
        include("apps.traffic_routing.public_urls"),
    ),
    # This shouldn't be exposed outside
    path(
        f"{internal_path_prefix}/apps/",
        include("apps.traffic_routing.internal_urls"),
    ),
]
