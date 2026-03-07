from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import ConnectorInstanceViewSet as CIViewSet

connector_list = CIViewSet.as_view({"get": "list", "post": "create"})
connector_detail = CIViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)
connector_users = CIViewSet.as_view({"get": "list_of_shared_users"})
connector_add_owner = CIViewSet.as_view({"post": "add_co_owner"})
connector_remove_owner = CIViewSet.as_view({"delete": "remove_co_owner"})

urlpatterns = format_suffix_patterns(
    [
        path("connector/", connector_list, name="connector-list"),
        path("connector/<uuid:pk>/", connector_detail, name="connector-detail"),
        path(
            "connector/users/<uuid:pk>/",
            connector_users,
            name="connector-users",
        ),
        path(
            "connector/<uuid:pk>/owners/",
            connector_add_owner,
            name="connector-add-owner",
        ),
        path(
            "connector/<uuid:pk>/owners/<int:user_id>/",
            connector_remove_owner,
            name="connector-remove-owner",
        ),
    ]
)
