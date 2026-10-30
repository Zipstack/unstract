from django.apps import AppConfig


class AccountConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "account_v2"

    def ready(self):
        import account_v2.signals  # noqa: F401
