from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from api_v2.api_deployment_views import APIDeploymentViewSet, DeploymentExecution
from api_v2.api_key_views import APIKeyViewSet

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
by_prompt_studio_tool = APIDeploymentViewSet.as_view(
    {
        "get": APIDeploymentViewSet.by_prompt_studio_tool.__name__,
    }
)
list_shared_users = APIDeploymentViewSet.as_view(
    {
        "get": APIDeploymentViewSet.list_of_shared_users.__name__,
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
            "deployment/<uuid:pk>/users/",
            list_shared_users,
            name="api_deployment_list_shared_users",
        ),
        path(
            "deployment/by-prompt-studio-tool/",
            by_prompt_studio_tool,
            name="api_deployment_by_prompt_studio_tool",
        ),
        path(
            "postman_collection/<uuid:pk>/",
            download_postman_collection,
            name="download_postman_collection",
        ),
        path("keys/<uuid:pk>/", key_details, name="key_details"),
        path("keys/api/<str:api_id>/", api_key, name="api_key_api"),
        path("keys/api/", api_key, name="api_keys_api"),
        path("keys/pipeline/<str:pipeline_id>/", api_key, name="api_key_pipeline"),
        path("keys/pipeline/", api_key, name="api_keys_pipeline"),
    ]
)
