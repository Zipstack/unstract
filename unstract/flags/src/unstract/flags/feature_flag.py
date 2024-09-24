"""Feature flag utils file."""

import logging
import os
from typing import Optional

from .client.evaluation import EvaluationClient

logger = logging.getLogger(__name__)


def check_feature_flag_status(
    flag_key: str,
    namespace_key: str = "default",
    entity_id: str = "unstract",
    context: Optional[dict[str, str]] = None,
) -> bool:
    """Check the status of a feature flag for a given entity.

    Args:
        namespace_key (str): The namespace key of the feature flag.
        flag_key (str): The flag key of the feature flag.
        entity_id (str): The ID of the entity for which the feature flag status
        is checked.
        context (dict, optional): Additional context data for evaluating the
        feature flag. Defaults to None.

    Returns:
        bool:
        True if the feature flag is enabled for the entity, False otherwise.
    """

    try:
        FLIPT_SERVICE_AVAILABLE = os.environ.get("FLIPT_SERVICE_AVAILABLE", False)
        if not FLIPT_SERVICE_AVAILABLE:
            return False

        evaluation_client = EvaluationClient()
        response = evaluation_client.boolean_evaluate_feature_flag(
            namespace_key=namespace_key,
            flag_key=flag_key,
            entity_id=entity_id,
            context=context,
        )
        return bool(response)  # Wrap the response in a boolean check
    except Exception:
        return False
