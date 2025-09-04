"""API communication layer for workers.

This package provides all API-related functionality including clients,
authentication, and backward compatibility facades.
"""

# Import facades for backward compatibility
from .facades.legacy_client import InternalAPIClient

__all__ = [
    # Main client facade for backward compatibility
    "InternalAPIClient",
]
