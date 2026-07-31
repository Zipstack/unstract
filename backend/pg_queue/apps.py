from django.apps import AppConfig


class PgQueueConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pg_queue"
    verbose_name = "PG Queue"
