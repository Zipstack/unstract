"""Feature flag utils file."""

from typing import Optional

from unstract.flags.clients.evaluation_client import EvaluationClient
from unstract.flags.clients.flipt_client import FliptClient


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
        evaluation_client = EvaluationClient()
        response = evaluation_client.boolean_evaluate_feature_flag(
            namespace_key=namespace_key,
            flag_key=flag_key,
            entity_id=entity_id,
            context=context,
        )
        return bool(response)  # Wrap the response in a boolean check
    except Exception as e:
        print(f"Error: {str(e)}")
        return False


def list_all_flags(
    namespace_key: str,
) -> dict:
    try:
        flipt_client = FliptClient()
        response = flipt_client.list_feature_flags(
            namespace_key=namespace_key,
        )
        return response
    except Exception as e:
        print(f"Error: {str(e)}")
        return {}
