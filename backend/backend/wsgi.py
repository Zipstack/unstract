"""WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv() or "")

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.platform"),
)

from django.conf import settings  # noqa: E402
from django.core.wsgi import get_wsgi_application  # noqa: E402
from utils.log_events import start_server  # noqa: E402

django_app = get_wsgi_application()

application = start_server(django_app, f"{settings.PATH_PREFIX}/socket")
