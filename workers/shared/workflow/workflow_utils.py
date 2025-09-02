"""Workflow Utility Functions

Common workflow-related utilities used across workers.
"""

import logging
from typing import TYPE_CHECKING

from unstract.core.data_models import WorkflowType

if TYPE_CHECKING:
    from shared.api_client import InternalAPIClient

logger = logging.getLogger(__name__)


def detect_comprehensive_workflow_type(
    api_client: "InternalAPIClient", workflow_id: str
) -> tuple[str, bool]:
    """Detect workflow type (API/ETL/TASK) by examining source and destination endpoints.

    This matches the backend pattern in workflow_helper.py and source.py:
    - API workflows: Source=API -> Destination=API
    - ETL workflows: Source=FILESYSTEM -> Destination=DATABASE
    - TASK workflows: Source=FILESYSTEM -> Destination=FILESYSTEM/other

    Args:
        api_client: Internal API client
        workflow_id: Workflow ID

    Returns:
        tuple: (workflow_type: str, is_api: bool)
    """
    try:
        # Get workflow endpoints to determine types
        workflow_endpoints = api_client.get_workflow_endpoints(workflow_id)

        if isinstance(workflow_endpoints, dict):
            endpoints = workflow_endpoints.get("endpoints", [])

            # Find source and destination endpoints
            source_connection_type = None
            dest_connection_type = None

            for endpoint in endpoints:
                if endpoint.get("endpoint_type") == "SOURCE":
                    source_connection_type = endpoint.get("connection_type")
                elif endpoint.get("endpoint_type") == "DESTINATION":
                    dest_connection_type = endpoint.get("connection_type")

            # Determine workflow type based on endpoint combinations
            if source_connection_type == "API":
                return WorkflowType.API, True
            elif dest_connection_type == "DATABASE":
                return WorkflowType.ETL, False
            elif source_connection_type == "FILESYSTEM":
                return WorkflowType.TASK, False
            else:
                logger.warning(
                    f"Unknown endpoint combination: source={source_connection_type}, dest={dest_connection_type}"
                )
                return WorkflowType.TASK, False

        # Fallback: use legacy API detection
        elif isinstance(workflow_endpoints, dict) and workflow_endpoints.get(
            "has_api_endpoints", False
        ):
            return WorkflowType.API, True
        else:
            return WorkflowType.TASK, False

    except Exception as e:
        logger.warning(
            f"Failed to detect comprehensive workflow type for {workflow_id}: {e} - defaulting to {WorkflowType.TASK}"
        )
        return WorkflowType.TASK, False
