from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import NotificationViewSet

notification_list = NotificationViewSet.as_view({"get": "list", "post": "create"})
notification_detail = NotificationViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    }
)

urlpatterns = format_suffix_patterns(
    [
        path("", notification_list, name="notification-list"),
        path("<uuid:pk>/", notification_detail, name="notification-detail"),
        path(
            "pipeline/<uuid:pipeline_uuid>/",
            notification_list,
            name="pipeline-notification-list",
        ),
        path("api/<uuid:api_uuid>/", notification_list, name="api-notification-list"),
    ]
)
