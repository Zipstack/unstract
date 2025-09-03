import logging
from datetime import date, datetime, time, timedelta
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
    def _get_subscription_dates(organization_id):
        """Attempt to get trial dates from subscription plugin.

        Assumes subscription plugin returns timezone-aware datetimes or dates
        that can be safely used without normalization (uniform storage).
        """
        try:
            from pluggable_apps.subscription_v2.subscription_helper import (
                SubscriptionHelper,
            )
        except (ImportError, ModuleNotFoundError):
            logger.debug("Subscription plugin not available, using fallback dates")
            return None, None

        # Plugin is available, attempt to get subscription data
        try:
            org_plans = SubscriptionHelper.get_subscription(organization_id)
        except AttributeError as e:
            logger.warning(f"Subscription plugin missing expected methods: {e}")
            return None, None

        if (
            not org_plans
            or not hasattr(org_plans, "start_date")
            or not hasattr(org_plans, "end_date")
        ):
            return None, None

        # If subscription returns dates, convert to datetime with proper times
        start_date = org_plans.start_date
        end_date = org_plans.end_date

        # Handle date objects by converting to start/end of day (assuming UTC)
        if isinstance(start_date, date) and not isinstance(start_date, datetime):
            start_date = datetime.combine(start_date, time.min).replace(
                tzinfo=timezone.utc
            )
        if isinstance(end_date, date) and not isinstance(end_date, datetime):
            end_date = datetime.combine(end_date, time.max).replace(tzinfo=timezone.utc)

        logger.info(f"Using subscription dates for org {organization_id}")
        return start_date, end_date

    @staticmethod
    def _calculate_usage_metrics(organization, trial_start_date, trial_end_date):
        """Calculate usage metrics for the trial period."""
        usage_queryset = Usage.objects.filter(
            organization=organization,
            created_at__gte=trial_start_date,
            created_at__lte=trial_end_date,
        )

        aggregated_data = usage_queryset.aggregate(
            total_cost=Sum("cost_in_dollars"),
            total_tokens=Sum("total_tokens"),
            unique_runs=Count("run_id", distinct=True),
            api_calls=Count("id"),
        )

        documents_processed = (
            usage_queryset.values("workflow_id", "execution_id").distinct().count()
        )

        return aggregated_data, documents_processed

    @staticmethod
    def get_trial_statistics(organization) -> dict[str, Any]:
        """Get comprehensive trial usage statistics for an organization.

        Args:
            organization: The organization object for which to retrieve trial statistics.
                         Must have 'organization_id' and 'created_at' attributes.

        Returns:
            dict: A dictionary containing comprehensive trial usage statistics with keys:
                - trial_start_date (str): ISO formatted trial start date
                - trial_end_date (str): ISO formatted trial end date
                - total_cost (float): Total cost in dollars during trial period
                - documents_processed (int): Number of unique document processing operations
                - api_calls (int): Total number of API calls made
                - etl_runs (int): Number of unique ETL pipeline runs
                - error (str, optional): Error message if processing fails
        """
        try:
            # Try to get subscription dates
            trial_start_date, trial_end_date = UsageHelper._get_subscription_dates(
                organization.organization_id
            )

            # Use fallback dates if needed (assuming uniform UTC storage)
            if not trial_start_date:
                trial_start_date = organization.created_at

            if not trial_end_date:
                # For end date, set to end of day (23:59:59.999999)
                end_of_trial_date = organization.created_at + timedelta(days=14)
                trial_end_date = end_of_trial_date.replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            # Validate trial window - guard against inverted date range
            if trial_end_date < trial_start_date:
                raise ValueError("trial_end_date must be on or after trial_start_date")

            # Calculate usage metrics
            aggregated_data, documents_processed = UsageHelper._calculate_usage_metrics(
                organization, trial_start_date, trial_end_date
            )

            return {
                "trial_start_date": trial_start_date.isoformat(),
                "trial_end_date": trial_end_date.isoformat(),
                "total_cost": aggregated_data.get("total_cost", 0) or 0,
                "documents_processed": documents_processed,
                "api_calls": aggregated_data.get("api_calls", 0) or 0,
                "etl_runs": aggregated_data.get("unique_runs", 0) or 0,
            }

        except Exception:
            logger.exception("Error calculating trial statistics")
            raise
