"""WSGI config for backend project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

import socketio
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from dotenv import load_dotenv
from log_events.views import sio

load_dotenv()
path_prefix = settings.PATH_PREFIX 

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)
django_app = get_wsgi_application()
application = socketio.WSGIApp(sio, django_app,socketio_path=f"{path_prefix}/socket")
