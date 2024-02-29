from apps.app_deployment.views import AppDeploymentView
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

deployment = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.list.__name__,
        "post": AppDeploymentView.create.__name__,
    }
)
deployment_details = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.retrieve.__name__,
        # Disabling updates for the time being
        # "put": AppDeploymentView.update.__name__,
        # "patch": AppDeploymentView.partial_update.__name__,
        "delete": AppDeploymentView.destroy.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("app/", deployment, name="app_deployment"),
        path(
            "app/<uuid:pk>/",
            deployment_details,
            name="app_deployment_details",
        ),
    ]
)
