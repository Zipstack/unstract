from workflow_manager.endpoint_v2.destination import DestinationConnector
from workflow_manager.endpoint_v2.models import WorkflowEndpoint
from workflow_manager.endpoint_v2.source import SourceConnector
from workflow_manager.workflow_v2.models.workflow import Workflow
from workflow_manager.workflow_v2.workflow_helper import WorkflowHelper


class WorkflowEndpointUtils:
    @staticmethod
    def create_endpoints_for_workflow(workflow: Workflow) -> None:
        """Create endpoints for a given workflow. This method creates both
        source and destination endpoints for the specified workflow.

        Parameters:
            workflow (Workflow): The workflow for which
                the endpoints need to be created.

        Returns:
            None
        """
        SourceConnector.create_endpoint_for_workflow(workflow)
        DestinationConnector.create_endpoint_for_workflow(workflow)

    @staticmethod
    def get_endpoints_for_workflow(workflow_id: str) -> list[WorkflowEndpoint]:
        workflow = WorkflowHelper.get_workflow_by_id(workflow_id)
        endpoints: list[WorkflowEndpoint] = WorkflowEndpoint.objects.filter(
            workflow=workflow
        )
        return endpoints
