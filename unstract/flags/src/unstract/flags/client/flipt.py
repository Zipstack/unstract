"""Flipt client wrapper for feature flag management."""

import logging
import os
import warnings
from deprecated import deprecated

from typing import Optional

from ..flipt_grpc.client import FliptGrpcClient, GrpcClientOptions

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
        self.eval_ip = os.environ.get("EVALUATION_SERVER_IP")
        self.eval_port = os.environ.get("EVALUATION_SERVER_PORT")
        self.flipt_url = f"{self.eval_ip}:{self.eval_port}"
        self.namespace_key = os.environ.get("UNSTRACT_FEATURE_FLAG_NAMESPACE", "default")
        self.grpc_opts = GrpcClientOptions(
            address=self.flipt_url,
            namespace_key=self.namespace_key
        )

    @deprecated("namespace_key is no longer used")
    def evaluate_boolean(
        self,
        flag_key: str,
        entity_id: Optional[str] = "unstract",
        context: Optional[dict] = None,
        namespace_key: Optional[str] = None
    ) -> bool:
        """Evaluate a boolean feature flag for a given entity.

        Args:
            flag_key: The key of the feature flag to evaluate
            entity_id: The ID of the entity for which to evaluate the flag
            context: Additional context for evaluation
            namespace_key: The namespace to evaluate the flag in
        Returns:
            bool: The evaluated boolean value of the feature flag
        """
        if namespace_key is not None:
            warnings.warn(
                "namespace_key parameter is deprecated and will be ignored",
                DeprecationWarning,
                stacklevel=2
            )
        if not self.service_available:
            logger.warning("Flipt service not available, returning False for all flags")
            return False

        client = None
        try:
            # Create a FliptClient instance for this specific namespace
            client = FliptGrpcClient(
                opts=self.grpc_opts
            )

            # Evaluate the boolean flag from the Flipt server
            result = client.evaluate_boolean(
                flag_key=flag_key,
                entity_id=entity_id,
                context=context or {}
            )

            return result.value if hasattr(result, "value") else False

        except Exception as e:
            logger.error(f"Error evaluating flag {flag_key} for entity {entity_id}: {e}")
            return False
        finally:
            # Always close the client to free resources
            if client:
                try:
                    client.close()
                except Exception as e:
                    logger.error(f"Error closing Flipt client: {e}")

    @deprecated("namespace_key is no longer used")
    def list_feature_flags(self, namespace_key: Optional[str] = None) -> dict:
        """List all feature flags in a namespace.

        Args:
            namespace_key: The namespace to list flags from

        Returns:
            dict: Dictionary containing flags and total_count
                Format: {"flags": {flag_key: enabled_status}, "total_count": int}
        """
        if namespace_key is not None:
            warnings.warn(
                "namespace_key parameter is deprecated and will be ignored",
                DeprecationWarning,
                stacklevel=2
            )
        if not self.service_available:
            logger.warning("Flipt service not available, returning empty flags")
            return {"flags": {}, "total_count": 0}

        client = None
        try:
            # Create a FliptClient instance for this specific namespace
            client = FliptGrpcClient(
                opts=self.grpc_opts
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