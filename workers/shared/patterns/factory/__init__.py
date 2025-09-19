"""Factory patterns for workers.

This package provides factory implementations following the Factory
pattern for creating various worker components.
"""

from .client_factory import InternalAPIClientFactory

__all__ = ["InternalAPIClientFactory"]
