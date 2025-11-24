"""WebSocket routing for Agentic Studio real-time progress updates."""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        r"ws/agentic/projects/(?P<project_id>[0-9a-f-]+)/progress/$",
        consumers.ProgressConsumer.as_asgi(),
    ),
]
