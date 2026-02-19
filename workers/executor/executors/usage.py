"""Usage tracking helper for the executor worker.

Ported from prompt-service/.../helpers/usage.py.
Flask/DB dependencies removed — usage data is pushed via the SDK1
``Audit`` class (HTTP to platform API) and returned directly in
``ExecutionResult.metadata`` instead of querying the DB.

Note: The SDK1 adapters (LLM, EmbeddingCompat) already call
``Audit().push_usage_data()`` internally.  This helper is for
explicit push calls outside of adapter operations (e.g. rent rolls).
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UsageHelper:
    @staticmethod
    def push_usage_data(
        event_type: str,
        kwargs: dict[str, Any],
        platform_api_key: str,
        token_counter: Any = None,
        model_name: str = "",
    ) -> bool:
        """Push usage data to the audit service.

        Wraps ``Audit().push_usage_data()`` with validation and
        error handling.

        Args:
            event_type: Type of usage event (e.g. "llm", "embedding").
            kwargs: Context dict (run_id, execution_id, etc.).
            platform_api_key: API key for platform service auth.
            token_counter: Token counter with usage metrics.
            model_name: Name of the model used.

        Returns:
            True if successful, False otherwise.
        """
        if not kwargs or not isinstance(kwargs, dict):
            logger.error("Invalid kwargs provided to push_usage_data")
            return False

        if not platform_api_key or not isinstance(platform_api_key, str):
            logger.error("Invalid platform_api_key provided to push_usage_data")
            return False

        try:
            from unstract.sdk1.audit import Audit

            logger.debug(
                "Pushing usage data for event_type=%s model=%s",
                event_type,
                model_name,
            )

            Audit().push_usage_data(
                platform_api_key=platform_api_key,
                token_counter=token_counter,
                model_name=model_name,
                event_type=event_type,
                kwargs=kwargs,
            )

            logger.info("Successfully pushed usage data for %s", model_name)
            return True
        except Exception:
            logger.exception("Error pushing usage data")
            return False

    @staticmethod
    def format_float_positional(value: float, precision: int = 10) -> str:
        """Format a float without scientific notation.

        Removes trailing zeros for clean display of cost values.
        """
        formatted: str = f"{value:.{precision}f}"
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
