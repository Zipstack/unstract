import logging
from datetime import datetime
from typing import Any, Optional

from django.db.models import QuerySet, Sum
from rest_framework.exceptions import APIException

from .constants import UsageKeys
from .models import Usage

logger = logging.getLogger(__name__)


class UsageHelper:
    @staticmethod
    def get_aggregated_token_count(run_id: str) -> dict:
        """Retrieve aggregated token counts for the given run_id.

        Args:
            run_id (str): The identifier for the token usage.

        Returns:
            dict: A dictionary containing aggregated token counts
            for different token types.
                  Keys:
                    - 'embedding_tokens': Total embedding tokens.
                    - 'prompt_tokens': Total prompt tokens.
                    - 'completion_tokens': Total completion tokens.
                    - 'total_tokens': Total tokens.

        Raises:
            APIException: For unexpected errors during database operations.
        """
        try:
            # Aggregate the token counts for the given run_id
            usage_summary = Usage.objects.filter(run_id=run_id).aggregate(
                embedding_tokens=Sum(UsageKeys.EMBEDDING_TOKENS),
                prompt_tokens=Sum(UsageKeys.PROMPT_TOKENS),
                completion_tokens=Sum(UsageKeys.COMPLETION_TOKENS),
                total_tokens=Sum(UsageKeys.TOTAL_TOKENS),
                cost_in_dollars=Sum(UsageKeys.COST_IN_DOLLARS),
            )

            logger.debug(f"Token counts aggregated successfully for run_id: {run_id}")

            # Prepare the result dictionary with None as the default value
            result = {
                UsageKeys.EMBEDDING_TOKENS: usage_summary.get(
                    UsageKeys.EMBEDDING_TOKENS
                ),
                UsageKeys.PROMPT_TOKENS: usage_summary.get(UsageKeys.PROMPT_TOKENS),
                UsageKeys.COMPLETION_TOKENS: usage_summary.get(
                    UsageKeys.COMPLETION_TOKENS
                ),
                UsageKeys.TOTAL_TOKENS: usage_summary.get(UsageKeys.TOTAL_TOKENS),
                UsageKeys.COST_IN_DOLLARS: usage_summary.get(UsageKeys.COST_IN_DOLLARS),
            }
            return result
        except Usage.DoesNotExist:
            # Handle the case where no usage data is found for the given run_id
            logger.warning(f"Usage data not found for the specified run_id: {run_id}")
            return {}
        except Exception as e:
            # Handle any other exceptions that might occur during the execution
            logger.error(f"An unexpected error occurred for run_id {run_id}: {str(e)}")
            raise APIException("Error while aggregating token counts")
        
    @staticmethod
    def get_aggregated_cost(execution_id: str) -> Optional[float]:
        """Retrieve aggregated cost for the given execution_id.

        Args:
            execution_id (str): The identifier for the total cost of a particular execution.

        Returns:
        Optional[float]: The total cost in dollars if available, else None.

        Raises:
            APIException: For unexpected errors during database operations.
        """
        try:
            # Aggregate the cost for the given execution_id
            total_cost = Usage.objects.filter(execution_id=execution_id).aggregate(
                cost_in_dollars=Sum(UsageKeys.COST_IN_DOLLARS)
            )[UsageKeys.COST_IN_DOLLARS]

            logger.debug(f"Cost aggregated successfully for execution_id: {execution_id}")

            return total_cost
        
        except Usage.DoesNotExist:
            # Handle the case where no usage data is found for the given execution_id
            logger.warning(f"Usage data not found for the specified execution_id: {execution_id}")
            return None
        except Exception as e:
            # Handle any other exceptions that might occur during the execution
            logger.error(f"An unexpected error occurred for execution_id {execution_id}: {str(e)}")
            raise APIException("Error while aggregating cost")

    @staticmethod
    def aggregate_usage_metrics(queryset: QuerySet) -> dict[str, Any]:
        """
        Aggregate usage metrics from a queryset of Usage objects.

        Args:
            queryset (QuerySet): A queryset of Usage objects.

        Returns:
            dict: A dictionary containing aggregated usage metrics.
        """
        return queryset.aggregate(
            total_prompt_tokens=Sum("prompt_tokens"),
            total_completion_tokens=Sum("completion_tokens"),
            total_tokens=Sum("total_tokens"),
            total_cost=Sum("cost_in_dollars"),
        )

    @staticmethod
    def format_usage_response(
        aggregated_data: dict[str, Any], start_date: datetime, end_date: datetime
    ) -> dict[str, Any]:
        """
        Format aggregated usage data into a structured response.

        Args:
            aggregated_data (dict): Aggregated usage metrics.
            start_date (datetime): Start date of the usage period.
            end_date (datetime): End date of the usage period.

        Returns:
            dict: Formatted response containing aggregated data and date range.
        """
        return {
            "aggregated_data": aggregated_data,
            "date_range": {"start_date": start_date, "end_date": end_date},
        }
