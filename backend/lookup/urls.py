"""URL configuration for Look-Up API endpoints."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    LookupDataSourceViewSet,
    LookupDebugView,
    LookupExecutionAuditViewSet,
    LookupProfileManagerViewSet,
    LookupProjectViewSet,
    LookupPromptTemplateViewSet,
    PromptStudioLookupLinkViewSet,
)

# Create router for viewsets
router = DefaultRouter()
router.register(r"lookup-projects", LookupProjectViewSet, basename="lookupproject")
router.register(
    r"lookup-templates", LookupPromptTemplateViewSet, basename="lookuptemplate"
)
router.register(r"lookup-profiles", LookupProfileManagerViewSet, basename="lookupprofile")
router.register(r"data-sources", LookupDataSourceViewSet, basename="lookupdatasource")
router.register(r"lookup-links", PromptStudioLookupLinkViewSet, basename="lookuplink")
router.register(
    r"execution-audits", LookupExecutionAuditViewSet, basename="executionaudit"
)
router.register(r"lookup-debug", LookupDebugView, basename="lookupdebug")

app_name = "lookup"

urlpatterns = [
    path("", include(router.urls)),
]
