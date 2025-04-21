from logging import Logger
from typing import Any

from flask import current_app as app
from unstract.prompt_service.constants import DBTableV2
from unstract.prompt_service.extensions import db, db_context
from unstract.prompt_service.utils.db_utils import DBUtils
from unstract.prompt_service.utils.env_loader import get_env_or_die


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
