from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "workflow_manager.workflow"

    def ready(self):
        from utils.log_events import log_received
        from workflow_manager.workflow.execution_log_utils import handle_received_log

        log_received.connect(handle_received_log)
