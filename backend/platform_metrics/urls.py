from django.urls import path

from .views import metrics

urlpatterns = [path("metrics", metrics, name="platform-metrics")]
