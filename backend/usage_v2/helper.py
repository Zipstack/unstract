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
    def normalize_to_timezone_aware_datetime(value, is_end_date=False, reference_tz=None):
        """Normalize a date or datetime to a timezone-aware datetime.

        Args:
            value: A date, naive datetime, or timezone-aware datetime object to normalize.
                  Can be None, in which case None is returned.
            is_end_date: If True and value is a date object, combine with time.max (23:59:59.999999)
                        to represent the end of the day. If False, combine with time.min (00:00:00).
                        This ensures proper date range inclusivity.
            reference_tz: Reference timezone to use for naive datetimes. If not provided,
                         defaults to UTC. All output datetimes will be in this timezone.

        Returns:
            A timezone-aware datetime object in the reference timezone, or None if input is None.

        """
        if value is None:
            return None

        # Use UTC as default timezone if no reference provided
        if reference_tz is None:
            reference_tz = timezone.utc

        # Handle date objects - convert to datetime with appropriate time
        if isinstance(value, date) and not isinstance(value, datetime):
            if is_end_date:
                # For end dates, use end of day (23:59:59.999999)
                value = datetime.combine(value, time.max.replace(microsecond=999999))
            else:
                # For start dates, use start of day (00:00:00)
                value = datetime.combine(value, time.min)

        # Handle datetime objects
        if isinstance(value, datetime):
            # If naive, make it timezone-aware using reference timezone
            if value.tzinfo is None:
                value = value.replace(tzinfo=reference_tz)
            # If already timezone-aware but different timezone, convert to reference
            elif reference_tz and value.tzinfo != reference_tz:
                value = value.astimezone(reference_tz)

        return value

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
    def _validate_organization(organization):
        """Validate organization has required attributes."""
        if not organization:
            raise ValueError("Organization cannot be None")
        if not hasattr(organization, "organization_id"):
            raise ValueError("Organization must have organization_id attribute")
        if not hasattr(organization, "created_at"):
            raise ValueError("Organization must have created_at attribute")

    @staticmethod
    def _get_reference_timezone(org_created_at):
        """Get reference timezone from organization or use UTC."""
        if hasattr(org_created_at, "tzinfo") and org_created_at.tzinfo:
            return org_created_at.tzinfo, org_created_at

        reference_tz = timezone.utc
        if org_created_at.tzinfo is None:
            org_created_at = org_created_at.replace(tzinfo=reference_tz)
        return reference_tz, org_created_at

    @staticmethod
    def _get_subscription_dates(organization_id, reference_tz):
        """Attempt to get trial dates from subscription plugin."""
        try:
            from pluggable_apps.subscription_v2.subscription_helper import (
                SubscriptionHelper,
            )

            org_plans = SubscriptionHelper.get_subscription(organization_id)
            if (
                not org_plans
                or not hasattr(org_plans, "start_date")
                or not hasattr(org_plans, "end_date")
            ):
                return None, None

            start_date = UsageHelper.normalize_to_timezone_aware_datetime(
                org_plans.start_date, is_end_date=False, reference_tz=reference_tz
            )
            end_date = UsageHelper.normalize_to_timezone_aware_datetime(
                org_plans.end_date, is_end_date=True, reference_tz=reference_tz
            )
            logger.info(f"Using subscription dates for org {organization_id}")
            return start_date, end_date

        except Exception as e:
            logger.info(
                f"Subscription plugin not available ({type(e).__name__}), using fallback dates"
            )
            return None, None

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
    def _get_error_response(organization):
        """Generate error response with fallback dates."""
        try:
            fallback_start = (
                organization.created_at
                if hasattr(organization, "created_at")
                else timezone.now()
            )
        except Exception:
            fallback_start = timezone.now()

        fallback_start = UsageHelper.normalize_to_timezone_aware_datetime(
            fallback_start, is_end_date=False, reference_tz=timezone.utc
        )
        fallback_end = UsageHelper.normalize_to_timezone_aware_datetime(
            fallback_start + timedelta(days=14),
            is_end_date=True,
            reference_tz=timezone.utc,
        )

        return {
            "error": "Failed to retrieve trial statistics",
            "trial_start_date": fallback_start.isoformat(),
            "trial_end_date": fallback_end.isoformat(),
            "total_cost": 0,
            "documents_processed": 0,
            "api_calls": 0,
            "etl_runs": 0,
        }

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
            # Validate organization
            UsageHelper._validate_organization(organization)

            # Get reference timezone
            reference_tz, org_created_at = UsageHelper._get_reference_timezone(
                organization.created_at
            )

            # Try to get subscription dates
            trial_start_date, trial_end_date = UsageHelper._get_subscription_dates(
                organization.organization_id, reference_tz
            )

            # Use fallback dates if needed
            if not trial_start_date:
                trial_start_date = UsageHelper.normalize_to_timezone_aware_datetime(
                    org_created_at, is_end_date=False, reference_tz=reference_tz
                )

            if not trial_end_date:
                trial_end_date = UsageHelper.normalize_to_timezone_aware_datetime(
                    org_created_at + timedelta(days=14),
                    is_end_date=True,
                    reference_tz=reference_tz,
                )

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

        except Exception as e:
            logger.error(f"Error calculating trial statistics: {str(e)}")
            return UsageHelper._get_error_response(organization)
