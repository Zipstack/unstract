"""Backward compatibility facades for API clients.

This package provides facades that maintain existing interfaces while
delegating to the new modular client architecture.
"""

# Re-export from parent for backward compatibility
from ..internal_client import InternalAPIClient

__all__ = ["InternalAPIClient"]
