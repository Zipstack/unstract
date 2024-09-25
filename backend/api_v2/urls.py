from api_v2.api_deployment_views import APIDeploymentViewSet, DeploymentExecution
from api_v2.api_key_views import APIKeyViewSet
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

deployment = APIDeploymentViewSet.as_view(
    {
        "get": APIDeploymentViewSet.list.__name__,
        "post": APIDeploymentViewSet.create.__name__,
    }
)
deployment_details = APIDeploymentViewSet.as_view(
    {
        "get": APIDeploymentViewSet.retrieve.__name__,
        "put": APIDeploymentViewSet.update.__name__,
        "patch": APIDeploymentViewSet.partial_update.__name__,
        "delete": APIDeploymentViewSet.destroy.__name__,
    }
)
download_postman_collection = APIDeploymentViewSet.as_view(
    {
        "get": APIDeploymentViewSet.download_postman_collection.__name__,
    }
)

execute = DeploymentExecution.as_view()

key_details = APIKeyViewSet.as_view(
    {
        "get": APIKeyViewSet.retrieve.__name__,
        "put": APIKeyViewSet.update.__name__,
        "delete": APIKeyViewSet.destroy.__name__,
    }
)
api_key = APIKeyViewSet.as_view(
    {
        "get": APIKeyViewSet.api_keys.__name__,
        "post": APIKeyViewSet.create.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("deployment/", deployment, name="api_deployment"),
        path(
            "deployment/<uuid:pk>/",
            deployment_details,
            name="api_deployment_details",
        ),
        path(
            "postman_collection/<uuid:pk>/",
            download_postman_collection,
            name="download_postman_collection",
        ),
        path("keys/<uuid:pk>/", key_details, name="key_details"),
        path("keys/api/<str:api_id>/", api_key, name="api_key"),
    ]
)
