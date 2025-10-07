"""Internal API URLs for Configuration access by workers."""

from django.urls import path

from . import internal_views

app_name = "configuration_internal"

urlpatterns = [
    path(
        "<str:config_key>/",
        internal_views.ConfigurationInternalView.as_view(),
        name="configuration-detail",
    ),
]
