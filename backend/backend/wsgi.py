"""WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import logging
import os
import time
import warnings

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from utils.log_events import start_server

logger = logging.getLogger(__name__)

# Suppress OpenTelemetry EventLogger LogRecord deprecation warning
# This is a bug in OpenTelemetry SDK 1.37.0 where EventLogger.emit() still uses
# deprecated trace_id/span_id/trace_flags parameters instead of context parameter.
# See: https://github.com/open-telemetry/opentelemetry-python/issues/4328
# TODO: Remove this suppression once OpenTelemetry fixes EventLogger.emit()
warnings.filterwarnings(
    "ignore",
    message="LogRecord init with.*trace_id.*span_id.*trace_flags.*deprecated",
    category=UserWarning,
)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

wsgi_start_time = time.perf_counter()
django_app = get_wsgi_application()
wsgi_init_elapsed = time.perf_counter() - wsgi_start_time
logger.info(f"WSGI application initialized in {wsgi_init_elapsed:.3f} seconds")


application = start_server(django_app, f"{settings.PATH_PREFIX}/socket")
