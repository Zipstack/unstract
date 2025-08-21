"""Internal API Constants

Centralized constants for internal API paths, versions, and configuration.
These constants can be overridden via environment variables for flexibility.
"""

import os

# Internal API Configuration
INTERNAL_API_PREFIX = os.getenv("INTERNAL_API_PREFIX", "/internal")
INTERNAL_API_VERSION = os.getenv("INTERNAL_API_VERSION", "v1")

# Computed full prefix
INTERNAL_API_BASE_PATH = f"{INTERNAL_API_PREFIX}/{INTERNAL_API_VERSION}"


def build_internal_endpoint(path: str) -> str:
    """Build a complete internal API endpoint path.

    Args:
        path: The endpoint path without the internal prefix (e.g., "health/")

    Returns:
        Complete internal API path (e.g., "/internal/v1/health/")
    """
    # Ensure path starts and ends with /
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.endswith("/"):
        path = f"{path}/"

    return f"{INTERNAL_API_BASE_PATH}{path}"


# Common endpoint builder shortcuts
class InternalEndpoints:
    """Convenience class for building internal API endpoints."""

    @staticmethod
    def health() -> str:
        """Health check endpoint."""
        return build_internal_endpoint("health")

    @staticmethod
    def workflow(workflow_id: str = "{id}") -> str:
        """Workflow endpoint."""
        return build_internal_endpoint(f"workflow/{workflow_id}")

    @staticmethod
    def workflow_status(workflow_id: str = "{id}") -> str:
        """Workflow status endpoint."""
        return build_internal_endpoint(f"workflow/{workflow_id}/status")

    @staticmethod
    def file_execution(file_execution_id: str = "{id}") -> str:
        """File execution endpoint."""
        return build_internal_endpoint(f"file-execution/{file_execution_id}")

    @staticmethod
    def file_execution_status(file_execution_id: str = "{id}") -> str:
        """File execution status endpoint."""
        return build_internal_endpoint(f"file-execution/{file_execution_id}/status")

    @staticmethod
    def webhook_send() -> str:
        """Webhook send endpoint."""
        return build_internal_endpoint("webhook/send")

    @staticmethod
    def organization(org_id: str = "{org_id}") -> str:
        """Organization endpoint."""
        return build_internal_endpoint(f"organization/{org_id}")


# Environment variable documentation
ENVIRONMENT_VARIABLES = {
    "INTERNAL_API_PREFIX": {
        "description": "Base prefix for internal API endpoints",
        "default": "/internal",
        "example": "/internal",
    },
    "INTERNAL_API_VERSION": {
        "description": "API version for internal endpoints",
        "default": "v1",
        "example": "v1",
    },
}


def get_api_info() -> dict:
    """Get current internal API configuration info."""
    return {
        "prefix": INTERNAL_API_PREFIX,
        "version": INTERNAL_API_VERSION,
        "base_path": INTERNAL_API_BASE_PATH,
        "environment_variables": ENVIRONMENT_VARIABLES,
    }
