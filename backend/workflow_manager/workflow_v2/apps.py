from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workflow_manager.workflow_v2"

    def ready(self):
        from workflow_manager.workflow_v2.execution_log_utils import (
            create_log_consumer_scheduler_if_not_exists,
        )

        create_log_consumer_scheduler_if_not_exists()
