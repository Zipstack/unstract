"""Internal API Client - Consolidated Implementation

This module provides a clean, consolidated API client by importing from
the modular facade implementation. This eliminates the previous 1,370+ lines
of duplicated code while maintaining backward compatibility.

All imports and functionality are now delegated to the specialized modular
clients through the facade pattern.
"""

# Import everything from the facade for full backward compatibility
from ..api.facades.legacy_client import (
    APIRequestError,
    AuthenticationError,
    FileExecutionCreateRequest,
    FileExecutionStatusUpdateRequest,
    FileHashData,
    InternalAPIClient,
    InternalAPIClientError,
    WorkflowFileExecutionData,
)

# Re-export for backward compatibility
__all__ = [
    "InternalAPIClient",
    "InternalAPIClientError",
    "AuthenticationError",
    "APIRequestError",
    "WorkflowFileExecutionData",
    "FileHashData",
    "FileExecutionCreateRequest",
    "FileExecutionStatusUpdateRequest",
]
