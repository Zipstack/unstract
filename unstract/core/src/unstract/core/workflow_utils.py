"""Workflow utility functions shared between backend and workers.

This module provides common utilities for workflow operations that need
to be consistent between Django backend and Celery workers.
"""

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class WorkflowConnectionTypes:
    """Workflow connection type constants."""

    FILESYSTEM = "FILESYSTEM"
    DATABASE = "DATABASE"
    API = "API"
    APPDEPLOYMENT = "APPDEPLOYMENT"
    MANUALREVIEW = "MANUALREVIEW"


class PipelineTypes:
    """Pipeline type constants matching backend models."""

    ETL = "ETL"
    TASK = "TASK"
    API = "API"
    APP = "APP"
    DEFAULT = "DEFAULT"


class WorkflowTypeDetector:
    """Detects workflow and pipeline types using consistent logic.

    This class provides methods to determine workflow types, pipeline types,
    and connection types that work consistently between backend and workers.
    """

    @staticmethod
    def get_pipeline_type_from_response(api_response: Any) -> str:
        """Extract pipeline type from API response.

        Args:
            api_response: Response from pipeline-type API endpoint (dict or response object)

        Returns:
            Pipeline type (API, ETL, TASK, APP, or DEFAULT)
        """
        # Handle both new response objects and legacy dict responses
        if hasattr(api_response, "success"):
            # New APIResponse object
            if not api_response.success:
                raise Exception(
                    f"Pipeline type API failed: {api_response.error or api_response.message}"
                )
            response_data = api_response.data or {}
        else:
            # Legacy dict response
            response_data = api_response or {}

        return response_data.get("pipeline_type", PipelineTypes.ETL)

    @staticmethod
    def is_api_deployment(pipeline_type: str) -> bool:
        """Check if pipeline type indicates an API deployment.

        Args:
            pipeline_type: Pipeline type string

        Returns:
            True if this is an API deployment
        """
        return pipeline_type == PipelineTypes.API

    @staticmethod
    def get_connection_type_from_endpoints(
        endpoints_response: dict[str, Any],
    ) -> tuple[str, bool]:
        """Determine connection type from workflow endpoints response.

        Args:
            endpoints_response: Response from workflow endpoints API

        Returns:
            Tuple of (connection_type, is_api_workflow)
        """
        # Check if workflow has API endpoints
        has_api_endpoints = endpoints_response.get("has_api_endpoints", False)

        if has_api_endpoints:
            return WorkflowConnectionTypes.API, True

        # Check destination endpoint type
        destination_endpoint = endpoints_response.get("destination_endpoint", {})
        connection_type = destination_endpoint.get(
            "connection_type", WorkflowConnectionTypes.FILESYSTEM
        )

        # API connection type also indicates API workflow
        is_api = connection_type == WorkflowConnectionTypes.API

        return connection_type, is_api

    @staticmethod
    def should_use_api_queue(
        pipeline_id: str | None, pipeline_type: str, connection_type: str
    ) -> bool:
        """Determine if workflow should use API deployment queue.

        Args:
            pipeline_id: Pipeline ID (may be None)
            pipeline_type: Pipeline type from API
            connection_type: Connection type from workflow endpoints

        Returns:
            True if should use API deployment queue
        """
        # API deployments always use API queue
        if WorkflowTypeDetector.is_api_deployment(pipeline_type):
            return True

        # Workflows with API connection type use API queue
        if connection_type == WorkflowConnectionTypes.API:
            return True

        # All others use general queue
        return False

    @staticmethod
    def get_queue_names(is_api_workflow: bool) -> tuple[str, str]:
        """Get appropriate queue names based on workflow type.

        Args:
            is_api_workflow: Whether this is an API workflow

        Returns:
            Tuple of (file_processing_queue, callback_queue)
        """
        if is_api_workflow:
            return "file_processing_lite", "file_processing_callback_lite"
        else:
            return "file_processing", "file_processing_callback"


class PipelineTypeResolver:
    """Resolves pipeline types using the improved logic.

    This class encapsulates the logic for determining pipeline types
    by checking APIDeployment first, then falling back to Pipeline model.
    """

    def __init__(self, api_client):
        """Initialize resolver with API client.

        Args:
            api_client: Internal API client instance
        """
        self.api_client = api_client
        self.logger = logger

    def get_pipeline_type(self, pipeline_id: str | UUID) -> dict[str, Any]:
        """Get pipeline type with improved logic.

        Checks APIDeployment table first, then Pipeline table.
        This ensures API deployments are correctly identified even if
        they also exist in the Pipeline table.

        Args:
            pipeline_id: Pipeline or API deployment ID

        Returns:
            Dictionary with pipeline type information
        """
        if not pipeline_id:
            return {
                "pipeline_type": PipelineTypes.ETL,
                "source": "default",
                "error": "No pipeline_id provided",
            }

        try:
            # Use the backend's pipeline-type endpoint which already implements
            # the correct logic (APIDeployment first, then Pipeline)
            # Pass organization_id to ensure proper access control
            org_id = self.api_client.organization_id
            self.logger.debug(
                f"Getting pipeline type for {pipeline_id} with organization_id: {org_id}"
            )

            response = self.api_client.get_pipeline_type(
                pipeline_id, organization_id=org_id
            )

            # Handle both new response objects and legacy dict responses
            if hasattr(response, "success"):
                # New APIResponse object
                if not response.success:
                    raise Exception(
                        f"Pipeline type API failed: {response.error or response.message}"
                    )
                response_data = response.data or {}
            else:
                # Legacy dict response
                response_data = response

            # Ensure we have the expected fields
            return {
                "pipeline_id": str(pipeline_id),
                "pipeline_type": response_data.get("pipeline_type", PipelineTypes.ETL),
                "source": response_data.get("source", "unknown"),
                "workflow_id": response_data.get("workflow_id"),
                "display_name": response_data.get("display_name"),
                "is_active": response_data.get("is_active", True),
                "is_api_deployment": response_data.get("pipeline_type")
                == PipelineTypes.API,
            }

        except Exception as e:
            # If pipeline not found (404), it's likely a workflow without a pipeline
            # This is normal for some workflows, so we return a default
            if "404" in str(e) or "not found" in str(e).lower():
                self.logger.debug(
                    f"Pipeline {pipeline_id} not found - likely a direct workflow execution"
                )
                return {
                    "pipeline_id": str(pipeline_id),
                    "pipeline_type": PipelineTypes.ETL,
                    "source": "not_found",
                    "error": "Pipeline not found - using default ETL type",
                    "is_api_deployment": False,
                }

            self.logger.error(f"Failed to get pipeline type for {pipeline_id}: {e}")
            return {
                "pipeline_id": str(pipeline_id),
                "pipeline_type": PipelineTypes.ETL,
                "source": "error",
                "error": str(e),
                "is_api_deployment": False,
            }

    def get_workflow_connection_type(self, workflow_id: str | UUID) -> dict[str, Any]:
        """Get workflow connection type from endpoints.

        Args:
            workflow_id: Workflow ID

        Returns:
            Dictionary with connection type information
        """
        try:
            # Get workflow endpoints to determine connection type
            endpoints = self.api_client.get_workflow_endpoints(workflow_id)

            connection_type, is_api = (
                WorkflowTypeDetector.get_connection_type_from_endpoints(endpoints)
            )

            return {
                "workflow_id": str(workflow_id),
                "connection_type": connection_type,
                "is_api_workflow": is_api,
                "has_api_endpoints": endpoints.get("has_api_endpoints", False),
                "source_endpoint": endpoints.get("source_endpoint"),
                "destination_endpoint": endpoints.get("destination_endpoint"),
            }

        except Exception as e:
            self.logger.error(
                f"Failed to get workflow connection type for {workflow_id}: {e}"
            )
            return {
                "workflow_id": str(workflow_id),
                "connection_type": WorkflowConnectionTypes.FILESYSTEM,
                "is_api_workflow": False,
                "error": str(e),
            }

    def should_route_to_api_worker(
        self, pipeline_id: str | UUID | None, workflow_id: str | UUID
    ) -> tuple[bool, dict[str, Any]]:
        """Determine if execution should be routed to API worker.

        This method intelligently checks workflow endpoints first as the primary method,
        then pipeline type if available to determine the correct worker routing.

        Args:
            pipeline_id: Pipeline ID (may be None)
            workflow_id: Workflow ID

        Returns:
            Tuple of (should_use_api_worker, routing_info)
        """
        routing_info = {
            "pipeline_id": str(pipeline_id) if pipeline_id else None,
            "workflow_id": str(workflow_id),
            "checks_performed": [],
        }

        # Check 1: Workflow connection type (primary method - always reliable)
        workflow_info = self.get_workflow_connection_type(workflow_id)
        routing_info["connection_type"] = workflow_info.get("connection_type")
        routing_info["has_api_endpoints"] = workflow_info.get("has_api_endpoints")
        routing_info["checks_performed"].append("workflow_endpoints")

        if workflow_info.get("is_api_workflow"):
            routing_info["routing_reason"] = "api_connection_type"
            routing_info["should_use_api_worker"] = True
            return True, routing_info

        # Check 2: Pipeline type (secondary method - may fail due to backend organization check issues)
        # Only check if pipeline_id provided and workflow isn't already identified as API
        if pipeline_id:
            pipeline_info = self.get_pipeline_type(pipeline_id)
            routing_info["pipeline_type"] = pipeline_info.get("pipeline_type")
            routing_info["pipeline_source"] = pipeline_info.get("source")
            routing_info["checks_performed"].append("pipeline_type")

            # Only consider valid pipeline type responses
            # Note: 'not_found' may occur due to backend organization validation issues
            if pipeline_info.get("source") not in ["not_found", "error"]:
                if pipeline_info.get("is_api_deployment"):
                    routing_info["routing_reason"] = "api_deployment"
                    routing_info["should_use_api_worker"] = True
                    return True, routing_info
            elif pipeline_info.get("source") == "not_found":
                # Log this as info, not error, as it may be due to organization validation
                self.logger.info(
                    f"Pipeline {pipeline_id} not found - may be due to organization validation. "
                    f"Falling back to workflow endpoint detection."
                )

        # Default: Route to general worker
        routing_info["routing_reason"] = "general_workflow"
        routing_info["should_use_api_worker"] = False
        return False, routing_info
