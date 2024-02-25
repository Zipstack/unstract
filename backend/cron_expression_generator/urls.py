from cron_expression_generator.views import CronViewSet
from django.urls import path
from rest_framework.urlpatterns import format_suffix_patterns

cron_generate = CronViewSet.as_view({"post": "generate"})
cron_clear_cache = CronViewSet.as_view({"get": "clear_cron_cache"})

urlpatterns = format_suffix_patterns(
    [
        path("cron/generate/", cron_generate, name="cron-generate"),
        path("cron/clear-cache/", cron_clear_cache, name="cron-clear-cache"),
    ]
)
