from django.apps import AppConfig


class ConnectionCheckConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "connection_check"
    verbose_name = "Connection Check"
