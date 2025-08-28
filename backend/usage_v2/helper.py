import logging
from datetime import datetime, timedelta
from typing import Any

from django.db.models import Count, QuerySet, Sum
from django.utils import timezone
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
                UsageKeys.EMBEDDING_TOKENS: usage_summary.get(UsageKeys.EMBEDDING_TOKENS),
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
    def aggregate_usage_metrics(queryset: QuerySet) -> dict[str, Any]:
        """Aggregate usage metrics from a queryset of Usage objects.

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
        """Format aggregated usage data into a structured response.

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

    @staticmethod
    def get_trial_statistics(organization) -> dict[str, Any]:
        """Get raw trial usage statistics for an organization.

        Args:
            organization: The organization object

        Returns:
            dict: A dictionary containing raw trial usage data
        """
        try:
            # Try to get subscription data if plugin is available
            trial_start_date = None
            trial_end_date = None

            try:
                from pluggable_apps.subscription_v2.subscription_helper import (
                    SubscriptionHelper,
                )

                org_plans = SubscriptionHelper.get_subscription(
                    organization.organization_id
                )
                if org_plans:
                    trial_start_date = org_plans.start_date
                    trial_end_date = org_plans.end_date
            except (ModuleNotFoundError, AttributeError):
                logger.info("Subscription plugin not found, using fallback dates")

            # Fallback to organization creation date for trial start if no subscription data
            if not trial_start_date:
                trial_start_date = organization.created_at

            # Fallback: assume 14-day trial period from organization creation if no subscription end date
            if not trial_end_date:
                trial_end_date = organization.created_at + timedelta(days=14)

            # Get all usage records for the organization during trial period
            usage_queryset = Usage.objects.filter(
                organization=organization,
                created_at__gte=trial_start_date,
                created_at__lte=trial_end_date,
            )

            # Calculate basic aggregations
            aggregated_data = usage_queryset.aggregate(
                total_cost=Sum("cost_in_dollars"),
                total_tokens=Sum("total_tokens"),
                unique_runs=Count("run_id", distinct=True),
                api_calls=Count("id"),
            )

            # Calculate documents processed (unique workflow + execution combinations)
            documents_processed = (
                usage_queryset.values("workflow_id", "execution_id").distinct().count()
            )

            # Return raw data with proper trial dates
            return {
                "trial_start_date": trial_start_date.isoformat(),
                "trial_end_date": trial_end_date.isoformat(),
                "total_cost": aggregated_data.get("total_cost", 0) or 0,
                "documents_processed": documents_processed,
                "api_calls": aggregated_data.get("api_calls", 0) or 0,
                "etl_runs": aggregated_data.get("unique_runs", 0) or 0,
            }

        except Exception as e:
            logger.error(f"Error calculating trial statistics: {str(e)}")
            # Return minimal error response with fallback dates
            fallback_start = (
                organization.created_at
                if hasattr(organization, "created_at")
                else timezone.now()
            )
            fallback_end = fallback_start + timedelta(days=14)

            return {
                "error": "Failed to retrieve trial statistics",
                "trial_start_date": fallback_start.isoformat(),
                "trial_end_date": fallback_end.isoformat(),
                "total_cost": 0,
                "documents_processed": 0,
                "api_calls": 0,
                "etl_runs": 0,
            }
