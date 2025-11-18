"""Flipt client wrapper for feature flag management."""

import logging
import os

from flipt_client import FliptClient as FliptSDKClient
from flipt_client.models import ClientOptions

logger = logging.getLogger(__name__)


class FliptClient:
    """Wrapper class for Flipt SDK client with convenience methods."""

    def __init__(self) -> None:
        """Initialize Flipt client wrapper."""
        # Check if Flipt service is available
        self.service_available = (
            os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() == "true"
        )

        if not self.service_available:
            logger.warning("Flipt service is not available")

        # Store configuration for creating clients
        self.flipt_url = os.environ.get("FLIPT_URL", "http://localhost:8080")

    def list_feature_flags(self, namespace_key: str) -> dict:
        """List all feature flags in a namespace.

        Args:
            namespace_key: The namespace to list flags from

        Returns:
            dict: Dictionary containing flags and total_count
                Format: {"flags": {flag_key: enabled_status}, "total_count": int}
        """
        if not self.service_available:
            logger.warning("Flipt service not available, returning empty flags")
            return {"flags": {}, "total_count": 0}

        client = None
        try:
            # Create a FliptClient instance for this specific namespace
            client = FliptSDKClient(
                opts=ClientOptions(namespace=namespace_key, url=self.flipt_url)
            )

            # List flags from the Flipt server
            response = client.list_flags()

            # Parse response into expected format
            parsed_flags = {}
            flags = response.flags if hasattr(response, "flags") else []

            for flag in flags:
                # Get enabled status (default to None if not available)
                enabled_status = flag.enabled if hasattr(flag, "enabled") else None
                parsed_flags[flag.key] = enabled_status

            total_count = (
                response.total_count if hasattr(response, "total_count") else len(flags)
            )

            return {"flags": parsed_flags, "total_count": total_count}

        except Exception as e:
            logger.error(f"Error listing flags for namespace {namespace_key}: {e}")
            return {"flags": {}, "total_count": 0}
        finally:
            # Always close the client to free resources
            if client:
                try:
                    client.close()
                except Exception as e:
                    logger.error(f"Error closing Flipt client: {e}")
