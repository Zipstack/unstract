"""Feature flag utils file."""

import logging

from .client.flipt import FliptClient

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
        # Initialize Flipt client
        client = FliptClient()

        logger.info(f"Client has been Initialised {client.list_feature_flags()}")

        # Evaluate boolean flag
        result = client.evaluate_boolean(
            flag_key=flag_key,
            entity_id=entity_id,
            context=context or {},
        )

        return bool(result)
    except Exception:
        return False
