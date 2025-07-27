"""Modular API Client Components

This package contains specialized API clients that have been extracted from the monolithic
InternalAPIClient to improve maintainability, testability, and performance.

Each client handles a specific domain of operations:
- BaseAPIClient: Core HTTP functionality, session management, retry logic
- ExecutionAPIClient: Workflow execution operations
- FileAPIClient: File execution and file history operations
- WebhookAPIClient: Webhook operations
- OrganizationAPIClient: Organization context management
- ToolAPIClient: Tool execution operations

For backward compatibility, the original InternalAPIClient is still available
as a facade that delegates to these specialized clients.
"""

from .base_client import BaseAPIClient
from .execution_client import ExecutionAPIClient
from .file_client import FileAPIClient
from .organization_client import OrganizationAPIClient
from .tool_client import ToolAPIClient
from .webhook_client import WebhookAPIClient

__all__ = [
    "BaseAPIClient",
    "ExecutionAPIClient",
    "FileAPIClient",
    "WebhookAPIClient",
    "OrganizationAPIClient",
    "ToolAPIClient",
]
