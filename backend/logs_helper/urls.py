from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import LogsHelperViewSet

logs_helper = LogsHelperViewSet.as_view({"get": "get_logs", "post": "store_log"})

urlpatterns = format_suffix_patterns(
    [
        path(
            "logs/",
            logs_helper,
            name="logs-helper",
        ),
    ]
)
