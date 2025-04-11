from workflow_manager.workflow_v2.models.execution import WorkflowExecution

from api_v2.models import APIDeployment
from api_v2.notification import APINotification


class APIDeploymentUtils:
    @staticmethod
    def get_api_by_id(api_id: str) -> APIDeployment | None:
        """Retrieves an APIDeployment instance by its unique ID.

        Args:
            api_id (str): The unique identifier of the APIDeployment to retrieve.

        Returns:
            Optional[APIDeployment]: The APIDeployment instance if found,
                otherwise None.
        """
        try:
            api_deployment: APIDeployment = APIDeployment.objects.get(pk=api_id)
            return api_deployment
        except APIDeployment.DoesNotExist:
            return None

    @staticmethod
    def send_notification(
        api: APIDeployment, workflow_execution: WorkflowExecution
    ) -> None:
        """Sends a notification for the specified API deployment and workflow
        execution.

        Args:
            api (APIDeployment): The APIDeployment instance for which the
                notification is being sent.
            workflow_execution (WorkflowExecution): The WorkflowExecution instance
                related to the notification.

        Returns:
            None
        """
        api_notification = APINotification(api=api, workflow_execution=workflow_execution)
        api_notification.send()
