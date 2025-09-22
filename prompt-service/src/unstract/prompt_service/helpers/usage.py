import logging
import traceback
from logging import Logger
from typing import Any

from flask import current_app as app

from unstract.flags.feature_flag import check_feature_flag_status

from unstract.prompt_service.constants import DBTableV2
from unstract.prompt_service.extensions import db, db_context
from unstract.prompt_service.utils.db_utils import DBUtils
from unstract.prompt_service.utils.env_loader import get_env_or_die
if check_feature_flag_status("sdk1"):
    from unstract.sdk1.audit import Audit
else:
    from unstract.sdk.audit import Audit

logger = logging.getLogger(__name__)


class UsageHelper:
    @staticmethod
    def query_usage_metadata(token: str, metadata: dict[str, Any]) -> dict[str, Any]:
        DB_SCHEMA = get_env_or_die("DB_SCHEMA", "unstract")
        organization_uid, org_id = DBUtils.get_organization_from_bearer_token(token)
        run_id: str = metadata["run_id"]
        query: str = f"""
            SELECT
                usage_type,
                llm_usage_reason,
                model_name,
                SUM(prompt_tokens) AS input_tokens,
                SUM(completion_tokens) AS output_tokens,
                SUM(total_tokens) AS total_tokens,
                SUM(embedding_tokens) AS embedding_tokens,
                SUM(cost_in_dollars) AS cost_in_dollars
            FROM "{DB_SCHEMA}"."{DBTableV2.TOKEN_USAGE}"
            WHERE run_id = %s and organization_id = %s
            GROUP BY usage_type, llm_usage_reason, model_name;
        """
        logger: Logger = app.logger
        try:
            logger.info(
                "Querying usage metadata for org_id: %s, run_id: %s", org_id, run_id
            )
            with db_context():
                with db.execute_sql(query, (run_id, organization_uid)) as cursor:
                    results: list[tuple] = cursor.fetchall()
                    # Process results as needed
                    for row in results:
                        key, item = UsageHelper._get_key_and_item(row)
                        # Initialize the key as an empty list if it doesn't exist
                        if key not in metadata:
                            metadata[key] = []
                        # Append the item to the list associated with the key
                        metadata[key].append(item)
        except Exception as e:
            logger.error(f"Error while querying usage metadata: {e}")
        return metadata

    @staticmethod
    def _get_key_and_item(row: tuple) -> tuple[str, dict[str, Any]]:
        (
            usage_type,
            llm_usage_reason,
            model_name,
            input_tokens,
            output_tokens,
            total_tokens,
            embedding_tokens,
            cost_in_dollars,
        ) = row
        cost_in_dollars: str = UsageHelper._format_float_positional(cost_in_dollars)
        key: str = usage_type
        item: dict[str, Any] = {
            "model_name": model_name,
            "cost_in_dollars": cost_in_dollars,
        }
        if llm_usage_reason:
            key = f"{llm_usage_reason}_{key}"
            item["input_tokens"] = input_tokens
            item["output_tokens"] = output_tokens
            item["total_tokens"] = total_tokens
        else:
            item["embedding_tokens"] = embedding_tokens
        return key, item

    @staticmethod
    def _format_float_positional(value: float, precision: int = 10) -> str:
        formatted: str = f"{value:.{precision}f}"
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted

    @staticmethod
    def push_usage_data(
        event_type: str,
        kwargs: dict[str, Any],
        platform_api_key: str,
        token_counter=None,
        model_name: str = "",
    ) -> bool:
        """Push usage data to the audit service.

        Args:
            event_type: Type of usage event being recorded
            kwargs: Additional data to include with the event
            platform_api_key: API key for authentication with the audit service
            token_counter: Token counter object with token usage metrics
            model_name: Name of the model used (if applicable)

        Returns:
            bool: True if successful, False otherwise
        Note:
            This method handles all exceptions internally and returns False on failure
            rather than propagating exceptions to the caller.
        """
        if not kwargs or not isinstance(kwargs, dict):
            logger.error("Invalid kwargs provided to push_usage_data")
            return False

        if not platform_api_key or not isinstance(platform_api_key, str):
            logger.error("Invalid platform_api_key provided to push_usage_data")
            return False

        try:
            logger.debug(
                f"Pushing usage data for event_type: {event_type}, model: {model_name}"
            )

            # Call the Audit SDK with the appropriate parameters
            Audit().push_usage_data(
                platform_api_key=platform_api_key,
                token_counter=token_counter,
                model_name=model_name,
                event_type=event_type,
                kwargs=kwargs,
            )

            logger.info(f"Successfully pushed usage data for {model_name}")
            return True
        except Exception as e:
            logger.exception(
                f"Error pushing usage data: {str(e)} - {traceback.format_exc()}"
            )
            return False
