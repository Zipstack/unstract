import logging

from django.db.models import Sum
from rest_framework.exceptions import APIException

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
                embedding_tokens=Sum("embedding_tokens"),
                prompt_tokens=Sum("prompt_tokens"),
                completion_tokens=Sum("completion_tokens"),
                total_tokens=Sum("total_tokens"),
            )

            logger.info(f"Token counts aggregated successfully for run_id: {run_id}")

            # Prepare the result dictionary with None as the default value
            result = {
                "embedding_tokens": usage_summary.get("embedding_tokens"),
                "prompt_tokens": usage_summary.get("prompt_tokens"),
                "completion_tokens": usage_summary.get("completion_tokens"),
                "total_tokens": usage_summary.get("total_tokens"),
            }
            return result
        except Usage.DoesNotExist:
            # Handle the case where no usage data is found for the given run_id
            logger.warning(f"Usage data not found for the specified run_id: {run_id}")
            return {}
        except Exception as e:
            # Handle any other exceptions that might occur during the execution
            logger.error(f"An unexpected error occurred for run_id {run_id}: {str(e)}")
            raise APIException(f"An unexpected error occurred: {str(e)}")
