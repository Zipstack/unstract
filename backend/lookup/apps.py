"""Lookup app configuration."""

from django.apps import AppConfig


class LookupConfig(AppConfig):
    """Configuration for the Lookup application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "lookup"
    verbose_name = "Look-Up System"
