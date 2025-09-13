"""Workflow API Client for Workflow Operations

This module provides specialized API client for workflow-related operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- Workflow definition retrieval
- Workflow execution management
- Workflow history operations
- Workflow batch operations
- Workflow status updates
- Workflow metadata management
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from shared.data.response_models import APIResponse, ResponseStatus

from unstract.core.data_models import (
    WorkflowDefinitionResponseData,
    WorkflowEndpointConfigResponseData,
)

from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


T = TypeVar("T")


@dataclass
class BaseWorkflowResponse(APIResponse, Generic[T]):
    """Base response class for all workflow operations with generic data typing."""

    workflow_id: str | UUID | None = None
    status: str = ResponseStatus.SUCCESS
    data: T | None = None

    @classmethod
    def success_response(
        cls,
        data: T | None = None,
        workflow_id: str | UUID | None = None,
        status: str = ResponseStatus.SUCCESS,
        message: str | None = None,
    ) -> "BaseWorkflowResponse[T]":
        """Create a successful response."""
        return cls(
            success=True,
            workflow_id=workflow_id,
            status=status,
            data=data,
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        workflow_id: str | UUID | None = None,
        status: str = ResponseStatus.ERROR,
        message: str | None = None,
    ) -> "BaseWorkflowResponse[T]":
        """Create an error response."""
        return cls(
            success=False,
            workflow_id=workflow_id,
            status=status,
            error=error,
            message=message,
        )

    def is_success(self) -> bool:
        """Check if the response indicates success."""
        return self.success_response and self.status == ResponseStatus.SUCCESS


@dataclass
class WorkflowDefinitionResponse(BaseWorkflowResponse[WorkflowDefinitionResponseData]):
    """Response for workflow definition operations."""

    pass


@dataclass
class WorkflowEndpointConfigResponse(
    BaseWorkflowResponse[WorkflowEndpointConfigResponseData]
):
    """Response for workflow endpoint configuration operations."""

    pass


class WorkflowOperationMixin:
    """Mixin providing common workflow operation utilities."""

    def _validate_workflow_id(self, workflow_id: str | UUID) -> str:
        """Validate and convert workflow ID to string."""
        if isinstance(workflow_id, UUID):
            return str(workflow_id)
        if not workflow_id or not isinstance(workflow_id, str):
            raise ValueError("workflow_id must be a non-empty string or UUID")
        try:
            # Validate it's a proper UUID format
            UUID(workflow_id)
            return workflow_id
        except ValueError:
            raise ValueError(f"Invalid workflow_id format: {workflow_id}")


class WorkflowAPIClient(BaseAPIClient, WorkflowOperationMixin):
    """Specialized API client for workflow-related operations.

    This client handles all workflow-related operations including:
    - Workflow definition retrieval
    - Workflow execution management
    - Workflow history operations
    - Workflow batch operations
    - Workflow status updates
    - Workflow metadata management
    """

    def get_workflow_definition(
        self, workflow_id: str | uuid.UUID, organization_id: str | None = None
    ) -> WorkflowDefinitionResponse:
        """Get workflow definition including workflow_type.

        Args:
            workflow_id: Workflow ID
            organization_id: Optional organization ID override

        Returns:
            WorkflowDefinitionResponse containing workflow definition data
        """
        try:
            validated_workflow_id = self._validate_workflow_id(workflow_id)
            # Use the workflow management internal API to get workflow details
            endpoint = f"v1/workflow-manager/workflow/{validated_workflow_id}/"
            response = self.get(endpoint, organization_id=organization_id)
            logger.info(
                f"Retrieved workflow definition for {validated_workflow_id}: {response.get('workflow_type', 'unknown')}"
            )
            return WorkflowDefinitionResponse.success_response(
                data=WorkflowDefinitionResponseData.from_dict(response),
                workflow_id=validated_workflow_id,
                message="Successfully retrieved workflow definition",
            )
        except Exception as e:
            logger.error(
                f"Failed to get workflow definition for {validated_workflow_id}: {str(e)}"
            )
            return WorkflowDefinitionResponse.error_response(
                error=str(e),
                workflow_id=validated_workflow_id,
                message="Failed to retrieve workflow definition",
            )

    def get_workflow_endpoints(
        self, workflow_id: str | UUID, organization_id: str | None = None
    ) -> WorkflowEndpointConfigResponse:
        """Get endpoint definition including endpoint_type.

        Args:
            workflow_id: Workflow ID
            organization_id: Optional organization ID override

        Returns:
            WorkflowEndpointConfigResponse containing workflow endpoint config data
        """
        try:
            validated_workflow_id = self._validate_workflow_id(workflow_id)
            # Use the workflow management internal API to get workflow details
            endpoint = f"v1/workflow-manager/{validated_workflow_id}/endpoint/"
            response = self.get(endpoint, organization_id=organization_id)
            logger.info(
                f"Retrieved workflow endpoints for {validated_workflow_id}: {response.get('workflow_type', 'unknown')}"
            )
            logger.info(f"DEBUG   get_workflow_endpoints  response: {response}")
            return WorkflowEndpointConfigResponse.success_response(
                workflow_id=validated_workflow_id,
                data=WorkflowEndpointConfigResponseData.from_dict(response),
                message="Successfully retrieved workflow endpoints",
            )
        except Exception as e:
            logger.error(
                f"Failed to get workflow endpoints for {validated_workflow_id}: {str(e)}"
            )
            return WorkflowEndpointConfigResponse.error_response(
                error=str(e),
                workflow_id=validated_workflow_id,
                message="Failed to retrieve workflow endpoints",
            )
