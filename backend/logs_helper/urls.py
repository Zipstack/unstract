from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

from .views import LogsHelperView

logs_helper_get = LogsHelperView.as_view({"get": "get_logs", "post": "store_log"})

urlpatterns = format_suffix_patterns(
    [
        path(
            "logs/",
            logs_helper_get,
            name="logs-helper-ping-pong",
        ),
    ]
)
