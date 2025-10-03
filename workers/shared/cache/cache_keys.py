"""Cache Key Generation Utilities

This module provides consistent cache key generation strategies for different
types of cached data (workflows, pipelines, API deployments, etc.).
"""

import hashlib


class CacheKeyGenerator:
    """Generates consistent cache keys for API operations."""

    @staticmethod
    def workflow_key(workflow_id: str) -> str:
        """Generate cache key for workflow data."""
        return f"worker_cache:workflow:{workflow_id}"

    @staticmethod
    def pipeline_key(pipeline_id: str) -> str:
        """Generate cache key for pipeline data."""
        return f"worker_cache:pipeline:{pipeline_id}"

    @staticmethod
    def api_deployment_key(api_id: str, org_id: str) -> str:
        """Generate cache key for API deployment data."""
        return f"worker_cache:api_deployment:{org_id}:{api_id}"

    @staticmethod
    def tool_instances_key(workflow_id: str) -> str:
        """Generate cache key for tool instances."""
        return f"worker_cache:tool_instances:{workflow_id}"

    @staticmethod
    def workflow_endpoints_key(workflow_id: str) -> str:
        """Generate cache key for workflow endpoints."""
        return f"worker_cache:workflow_endpoints:{workflow_id}"

    @staticmethod
    def custom_key(operation: str, *args: str) -> str:
        """Generate cache key for custom operations."""
        # Create a hash of the arguments for consistent keys
        # Using SHA-256 for SonarCloud compliance (cache key generation is not security-critical)
        args_hash = hashlib.sha256(":".join(args).encode()).hexdigest()[:8]
        return f"worker_cache:{operation}:{args_hash}"
