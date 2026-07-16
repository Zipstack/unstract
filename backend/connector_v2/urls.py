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
connector_share = CIViewSet.as_view({"post": "share"})
connector_effective_members = CIViewSet.as_view({"get": "effective_members"})

urlpatterns = format_suffix_patterns(
    [
        path("connector/", connector_list, name="connector-list"),
        path("connector/<uuid:pk>/", connector_detail, name="connector-detail"),
        path("connector/<uuid:pk>/share/", connector_share, name="connector-share"),
        path(
            "connector/<uuid:pk>/effective-members/",
            connector_effective_members,
            name="connector-effective-members",
        ),
    ]
)
