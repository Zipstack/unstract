from django.urls import path

from platform_audit.views import (
    PlatformAuditActionListView,
    PlatformAuditActorListView,
    PlatformAuditEventExportView,
    PlatformAuditEventListView,
)

urlpatterns = [
    path("", PlatformAuditEventListView.as_view(), name="platform_audit_event_list"),
    path(
        "export/",
        PlatformAuditEventExportView.as_view(),
        name="platform_audit_event_export",
    ),
    path(
        "actions/",
        PlatformAuditActionListView.as_view(),
        name="platform_audit_action_list",
    ),
    path(
        "actors/",
        PlatformAuditActorListView.as_view(),
        name="platform_audit_actor_list",
    ),
]
