"""API communication layer for workers.

This package provides all API-related functionality including clients,
authentication, and communication with the backend.
"""

# Import the main internal API client
from .internal_client import InternalAPIClient

__all__ = [
    # Main internal API client for backend communication
    "InternalAPIClient",
]
