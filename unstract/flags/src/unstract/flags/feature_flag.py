"""Feature flag utils file."""

import logging
import os

from flipt_client import FliptClient
from flipt_client.models import ClientOptions

logger = logging.getLogger(__name__)


def check_feature_flag_status(
    flag_key: str,
    namespace_key: str | None = None,
    entity_id: str = "unstract",
    context: dict[str, str] | None = None,
) -> bool:
    """Check the status of a feature flag for a given entity.

    Args:
        flag_key (str): The flag key of the feature flag.
        namespace_key (str | None): The namespace key of the feature flag.
            If None, the function will read the environment variable
            UNSTRACT_FEATURE_FLAG_NAMESPACE and fall back to "default".
        entity_id (str): The ID of the entity for which the feature flag status
            is checked.
        context (dict, optional): Additional context data for evaluating the
            feature flag. Defaults to None.

    Returns:
        bool:
        True if the feature flag is enabled for the entity, False otherwise.
    """
    try:
        # Resolve namespace: use provided value, or env var, or fallback.
        if namespace_key is None:
            namespace_key = os.environ.get("UNSTRACT_FEATURE_FLAG_NAMESPACE", "default")

        FLIPT_SERVICE_AVAILABLE = (
            os.environ.get("FLIPT_SERVICE_AVAILABLE", "false").lower() == "true"
        )
        if not FLIPT_SERVICE_AVAILABLE:
            return False

        # Get Flipt server URL from environment
        flipt_url = os.environ.get("FLIPT_URL", "http://localhost:8080")

        # Initialize Flipt client
        client = FliptClient(opts=ClientOptions(namespace=namespace_key, url=flipt_url))

        # Evaluate boolean flag
        result = client.evaluate_boolean(
            flag_key=flag_key,
            entity_id=entity_id,
            context=context or {},
        )

        # close client to save resources
        client.close()

        return bool(result.enabled)
    except Exception:
        return False
