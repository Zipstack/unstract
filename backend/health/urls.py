from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import health_check

urlpatterns = format_suffix_patterns(
    [path("health/", health_check, name="health-check")]
)
