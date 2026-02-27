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


def check_feature_flag_variant(
    flag_key: str,
    namespace_key: str | None = None,
    entity_id: str = "unstract",
    context: dict[str, str] | None = None,
) -> dict:
    """Check a variant feature flag and return its evaluation result.

    Evaluates a Flipt variant flag and returns the full evaluation response.
    The function first checks whether the flag is enabled before calling
    Flipt's variant evaluation API.

    Args:
        flag_key: The flag key of the feature flag.
        namespace_key: The namespace key of the feature flag.
            If None, reads UNSTRACT_FEATURE_FLAG_NAMESPACE env var,
            falling back to "default".
        entity_id: An identifier for the evaluation entity. Used by Flipt
            for consistent percentage-based rollout hashing only — it does
            NOT influence segment constraint matching.
        context: Key-value pairs matched against Flipt segment constraints.
            Keys must correspond exactly to the constraint property names
            configured in Flipt. For example, if a segment has a constraint
            on property "organization_id", pass
            ``{"organization_id": "org_123"}``. Defaults to None.

    Returns:
        dict with the following fields:

        - **enabled** (bool): Whether the flag is enabled in Flipt.
        - **match** (bool): Whether the entity matched a segment rule.
        - **variant_key** (str): The key of the matched variant (empty
          string if no match).
        - **variant_attachment** (str): JSON string attached to the variant
          (empty string if no match). Parse with ``json.loads()`` to get
          structured data.
        - **segment_keys** (list[str]): Segment keys that were matched.

    Result interpretation:
        - ``enabled=False`` → Flag is disabled or not found in Flipt.
          All other fields are at their defaults.
        - ``enabled=True, match=True`` → The entity's context matched a
          segment rule and a variant was assigned. ``variant_key`` and
          ``variant_attachment`` contain the assigned values.
        - ``enabled=True, match=False`` → The flag is on but no segment
          rule matched the provided context. This typically means Flipt
          is missing Segments and/or Rules for this flag, or the context
          keys/values don't satisfy any segment constraint.

    Note:
        Variant flags in Flipt require three things to be configured for
        ``match=True``: **Variants** (the possible values), **Segments**
        (constraint-based groups), and **Rules** (which link segments to
        variants). If any of these are missing, evaluation returns
        ``match=False``.

    Example::

        import json

        result = check_feature_flag_variant(
            flag_key="extraction_engine",
            context={"organization_id": "org_123"},
        )
        if result["enabled"] and result["match"]:
            config = json.loads(result["variant_attachment"])
            engine = config["engine"]
    """
    default_result = {
        "enabled": False,
        "match": False,
        "variant_key": "",
        "variant_attachment": "",
        "segment_keys": [],
    }
    try:
        client = FliptClient()

        # Check enabled status first
        flags = client.list_feature_flags()
        if not flags.get("flags", {}).get(flag_key, False):
            return default_result

        # Flag is enabled, evaluate variant
        result = client.evaluate_variant(
            flag_key=flag_key,
            entity_id=entity_id,
            context=context or {},
        )
        result["enabled"] = True

        return result
    except Exception:
        return default_result
