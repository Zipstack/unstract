from django.urls import path

from global_api_deployment_key.views import GlobalApiDeploymentKeyViewSet

urlpatterns = [
    path(
        "keys/",
        GlobalApiDeploymentKeyViewSet.as_view({"get": "list", "post": "create"}),
        name="global_api_deployment_key_list",
    ),
    path(
        "keys/<uuid:pk>/",
        GlobalApiDeploymentKeyViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="global_api_deployment_key_detail",
    ),
    path(
        "keys/<uuid:pk>/rotate/",
        GlobalApiDeploymentKeyViewSet.as_view({"post": "rotate"}),
        name="global_api_deployment_key_rotate",
    ),
    path(
        "deployments/",
        GlobalApiDeploymentKeyViewSet.as_view({"get": "deployments"}),
        name="global_api_deployment_key_deployments",
    ),
]
