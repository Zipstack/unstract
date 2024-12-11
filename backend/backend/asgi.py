"""ASGI config for backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv() or "")

load_dotenv()

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.platform"),
)

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()
