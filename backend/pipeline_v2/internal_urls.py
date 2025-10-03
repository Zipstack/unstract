"""Internal API URLs for Pipeline Operations"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .internal_api_views import (
    PipelineInternalViewSet,
)

# Create router for pipeline viewsets
router = DefaultRouter()
router.register(r"", PipelineInternalViewSet, basename="pipeline-internal")

urlpatterns = [
    # Pipeline internal APIs
    path("", include(router.urls)),
]
