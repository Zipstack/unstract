import logging

from django.db.models import Sum
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
