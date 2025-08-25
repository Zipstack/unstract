from django.apps import AppConfig


class WorkflowEndpointConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workflow_manager.endpoint_v2"

    def ready(self):
        # Import signals to ensure they are connected
        from workflow_manager.endpoint_v2 import signals  # noqa: F401
