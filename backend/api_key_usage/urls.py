from django.urls import path

from api_key_usage.views import KeyUsageSummaryView

urlpatterns = [
    path("summary/", KeyUsageSummaryView.as_view(), name="api_key_usage_summary"),
]
