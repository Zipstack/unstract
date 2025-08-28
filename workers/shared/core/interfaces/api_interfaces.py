"""API client interfaces following Interface Segregation Principle.

These interfaces define minimal contracts for API client implementations,
allowing for flexible and testable code.
"""

from abc import ABC, abstractmethod
from typing import Any


class APIClientInterface(ABC):
    """Base interface for API clients."""

    @abstractmethod
    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform GET request to API endpoint."""
        pass

    @abstractmethod
    def post(self, endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform POST request to API endpoint."""
        pass

    @abstractmethod
    def put(self, endpoint: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform PUT request to API endpoint."""
        pass

    @abstractmethod
    def delete(self, endpoint: str) -> dict[str, Any]:
        """Perform DELETE request to API endpoint."""
        pass

    @abstractmethod
    def set_organization_context(self, organization_id: str) -> None:
        """Set organization context for subsequent requests."""
        pass


class CacheInterface(ABC):
    """Interface for caching implementations."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Retrieve value from cache."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Store value in cache with optional TTL."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Remove value from cache."""
        pass

    @abstractmethod
    def clear(self) -> bool:
        """Clear all cached values."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass


class AuthenticationInterface(ABC):
    """Interface for authentication handlers."""

    @abstractmethod
    def authenticate(self) -> dict[str, str]:
        """Perform authentication and return headers."""
        pass

    @abstractmethod
    def refresh_token(self) -> bool:
        """Refresh authentication token if needed."""
        pass

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        pass
