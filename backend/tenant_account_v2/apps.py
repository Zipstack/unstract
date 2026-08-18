from django.apps import AppConfig


class TenantAccountV2Config(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tenant_account_v2"

    def ready(self):
        from tenant_account_v2 import checks, signals  # noqa: F401
