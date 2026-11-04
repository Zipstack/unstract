from django.apps import AppConfig


class ApiKeyUsageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api_key_usage"
    verbose_name = "API Key Usage"

    def ready(self) -> None:
        from api_key_usage.registry import register_builtin_key_types

        register_builtin_key_types()
