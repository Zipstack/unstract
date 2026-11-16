"""Internal API URLs for group-sharing email notifications."""

from django.urls import path

from . import internal_views

app_name = "group_notification_internal"

urlpatterns = [
    path(
        "resource-shared/",
        internal_views.ResourceSharedWithGroupView.as_view(),
        name="resource-shared",
    ),
    path(
        "membership-changed/",
        internal_views.GroupMembershipChangedView.as_view(),
        name="membership-changed",
    ),
]
