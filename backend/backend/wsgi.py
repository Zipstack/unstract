"""WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import logging
import os
import time

from django.conf import settings
from django.core.wsgi import get_wsgi_application
from utils.log_events import start_server

logger = logging.getLogger(__name__)

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

wsgi_start_time = time.perf_counter()
django_app = get_wsgi_application()
wsgi_init_elapsed = time.perf_counter() - wsgi_start_time
logger.info(f"WSGI application initialized in {wsgi_init_elapsed:.3f} seconds")


application = start_server(django_app, f"{settings.PATH_PREFIX}/socket")
