from django.apps import AppConfig


class InternalApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "internal_api"
    verbose_name = "Internal API"

    def ready(self):
        """Initialize internal API configuration when Django starts."""
        pass
