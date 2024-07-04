from django.urls import path
from pluggable_apps.apps.app_deployment.views import AppDeploymentView
from rest_framework.urlpatterns import format_suffix_patterns

deployment = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.list.__name__,
        "post": AppDeploymentView.create.__name__,
    }
)
deployment_detail = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.retrieve.__name__,
        "patch": AppDeploymentView.partial_update.__name__,
        "delete": AppDeploymentView.destroy.__name__,
    }
)


deployment_chats = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.list_chats.__name__,
    }
)

deployment_canned_question = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.list_canned_questions.__name__,
    }
)

deployment_documents = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.list_documents.__name__,
    }
)

app_users = AppDeploymentView.as_view(
    {
        "get": AppDeploymentView.list_of_shared_users.__name__,
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("", deployment, name="app_deployment"),
        path("<uuid:pk>/", deployment_detail, name="app_deployment_detail"),
        path(
            "chats/<str:app_id>/",
            deployment_chats,
            name="app_chat",
        ),
        path(
            "canned_question/<str:app_id>/",
            deployment_canned_question,
            name="app_canned_question",
        ),
        path(
            "documents/<str:app_id>/",
            deployment_documents,
            name="app_deployment_documents",
        ),
        path(
            "users/<uuid:pk>/",
            app_users,
            name="app_user",
        ),
    ]
)
