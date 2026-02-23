"""Usage API Client for Usage Operations

This module provides specialized API client for usage-related operations,
extracted from the monolithic InternalAPIClient to improve maintainability.

Handles:
- Token usage aggregation
- Usage statistics retrieval
- Usage metadata management
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Generic, TypeVar
from uuid import UUID

from shared.data.response_models import APIResponse, ResponseStatus
from unstract.core.data_models import UsageResponseData

from .base_client import BaseAPIClient

logger = logging.getLogger(__name__)


T = TypeVar("T")


@dataclass
class BaseUsageResponse(APIResponse, Generic[T]):
    """Base response class for all usage operations with generic data typing."""

    file_execution_id: str | UUID | None = None
    status: str = ResponseStatus.SUCCESS
    data: T | None = None

    @classmethod
    def success_response(
        cls,
        data: T | None = None,
        file_execution_id: str | UUID | None = None,
        status: str = ResponseStatus.SUCCESS,
        message: str | None = None,
    ) -> "BaseUsageResponse[T]":
        """Create a successful response."""
        return cls(
            success=True,
            file_execution_id=file_execution_id,
            status=status,
            data=data,
            message=message,
        )

    @classmethod
    def error_response(
        cls,
        error: str,
        file_execution_id: str | UUID | None = None,
        status: str = ResponseStatus.ERROR,
        message: str | None = None,
    ) -> "BaseUsageResponse[T]":
        """Create an error response."""
        return cls(
            success=False,
            file_execution_id=file_execution_id,
            status=status,
            error=error,
            message=message,
        )

    def is_success(self) -> bool:
        """Check if the response indicates success."""
        return self.success_response and self.status == ResponseStatus.SUCCESS


@dataclass
class UsageResponse(BaseUsageResponse[UsageResponseData]):
    """Response for usage operations."""

    pass


class UsageOperationMixin:
    """Mixin providing common usage operation utilities."""

    def _validate_file_execution_id(self, file_execution_id: str | UUID) -> str:
        """Validate and convert file execution ID to string."""
        if isinstance(file_execution_id, UUID):
            return str(file_execution_id)
        if not file_execution_id or not isinstance(file_execution_id, str):
            raise ValueError("file_execution_id must be a non-empty string or UUID")
        try:
            # Validate it's a proper UUID format
            UUID(file_execution_id)
            return file_execution_id
        except ValueError:
            raise ValueError(f"Invalid file_execution_id format: {file_execution_id}")


class UsageAPIClient(BaseAPIClient, UsageOperationMixin):
    """Specialized API client for usage-related operations.

    This client handles all usage-related operations including:
    - Token usage aggregation
    - Usage statistics retrieval
    - Usage metadata management
    """

    def get_aggregated_token_count(
        self, file_execution_id: str | uuid.UUID, organization_id: str | None = None
    ) -> UsageResponse:
        """Get aggregated token usage data for a file execution.

        Args:
            file_execution_id: File execution ID to get usage data for
            organization_id: Optional organization ID override

        Returns:
            UsageResponse containing aggregated usage data
        """
        try:
            validated_file_execution_id = self._validate_file_execution_id(
                file_execution_id
            )
            # Use the usage internal API to get aggregated token count
            endpoint = f"v1/usage/aggregated-token-count/{validated_file_execution_id}/"
            response = self.get(endpoint, organization_id=organization_id)

            logger.info(
                f"Retrieved usage data for {validated_file_execution_id}: {response.get('success', False)}"
            )

            if response and response.get("success"):
                # Extract usage data from the response
                usage_dict = response.get("data", {}).get("usage", {})
                usage_data = UsageResponseData(
                    file_execution_id=validated_file_execution_id,
                    embedding_tokens=usage_dict.get("embedding_tokens"),
                    prompt_tokens=usage_dict.get("prompt_tokens"),
                    completion_tokens=usage_dict.get("completion_tokens"),
                    total_tokens=usage_dict.get("total_tokens"),
                    cost_in_dollars=usage_dict.get("cost_in_dollars"),
                )
                return UsageResponse.success_response(
                    data=usage_data,
                    file_execution_id=validated_file_execution_id,
                    message="Successfully retrieved usage data",
                )
            else:
                logger.warning(
                    f"No usage data found for file_execution_id {validated_file_execution_id}"
                )
                # Return empty usage data instead of error for backward compatibility
                usage_data = UsageResponseData(
                    file_execution_id=validated_file_execution_id
                )
                return UsageResponse.success_response(
                    data=usage_data,
                    file_execution_id=validated_file_execution_id,
                    message="No usage data found, returning empty data",
                )

        except Exception as e:
            logger.error(
                f"Failed to get usage data for {validated_file_execution_id}: {str(e)}"
            )
            return UsageResponse.error_response(
                error=str(e),
                file_execution_id=validated_file_execution_id,
                message="Failed to retrieve usage data",
            )
