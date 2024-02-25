"""This module contains the Celery configuration for the backend
project."""

import os

from celery import Celery
from django.conf import settings

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.environ.get("DJANGO_SETTINGS_MODULE", "backend.settings.dev"),
)

# Create a Celery instance. Default time zone is UTC.
app = Celery("backend")

# Use Redis as the message broker.
app.conf.broker_url = settings.CELERY_BROKER_URL
app.conf.result_backend = settings.CELERY_RESULT_BACKEND

# Load task modules from all registered Django app configs.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in all installed apps.
app.autodiscover_tasks()

# Use the Django-Celery-Beat scheduler.
app.conf.beat_scheduler = "django_celery_beat.schedulers:DatabaseScheduler"
