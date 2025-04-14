import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from dateutil.parser import parse
from django.utils import timezone
from isodate import parse_datetime

from utils.date.enums import DateRangePresets
from utils.date.exceptions import InvalidDatetime

logger = logging.getLogger(__name__)


@dataclass
class DateRange:
    """Represents a validated date range with start and end dates.

    Attributes:
        start_date: Beginning of the date range
        end_date: End of the date range
    """

    start_date: datetime
    end_date: datetime


class DateTimeProcessor:
    DEFAULT_DAYS_RANGE = 1
    MAX_DAYS_RANGE = 60

    @staticmethod
    def normalize_datetime(date_str: str) -> str:
        """Converts various datetime string formats to ISO 8601 format.

        Args:
            date_input: A string representing a date/time in any recognizable format

        Returns:
            str: Normalized datetime string in ISO 8601 format (YYYY-MM-DDTHH:MM:SS)

        Raises:
            ValueError: If the input string cannot be parsed as a valid datetime
        """
        try:
            dt = parse(date_str)
            return dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError as e:
            logger.error(f"Error parsing datetime: {e}")
            raise InvalidDatetime(f"Invalid datetime format: {date_str}")

    @classmethod
    def parse_date_parameter(
        cls,
        date_param: str | datetime | None,
        default_date: datetime | None = None,
    ) -> datetime | None:
        """Parses and converts date parameters to datetime objects.

        Args:
            date_param: Date parameter that can be either a string or datetime object
            default_date: Fallback datetime value if date_param is None

        Returns:
            Optional[datetime]: Parsed datetime object or default_date if no valid input

        Examples:
            >>> DateTimeProcessor.parse_date_parameter("2023-12-01T10:00:00")
            datetime(2023, 12, 1, 10, 0)
        """
        if isinstance(date_param, str):
            normalized_date = cls.normalize_datetime(date_param)
            return parse_datetime(normalized_date)
        return date_param or default_date

    @classmethod
    def process_date_range(
        cls,
        start_date_param: str | datetime | None = None,
        end_date_param: str | datetime | None = None,
    ) -> DateRange:
        """Processes and validates start and end dates with smart defaults.

        Logic:
        1. If no end_date: use current time
        2. If no start_date: use end_date minus DEFAULT_DAYS_RANGE
        3. Validates the resulting range

        Args:
            start_date_param: Optional start date
            end_date_param: Optional end date

        Returns:
            DateRange: Object containing processed dates and validation status

        Examples:
            >>> # No dates provided - defaults to last 24 hours
            >>> range = DateTimeProcessor.process_date_range()
            >>> # Only end date - starts 24 hours before
            >>> range = DateTimeProcessor.process_date_range(
            ...     end_date_param="2023-12-01T00:00:00"
            ... )
            >>> # Both dates provided
            >>> range = DateTimeProcessor.process_date_range(
            ...     start_date_param="2023-11-01", end_date_param="2023-12-01"
            ... )
        """
        # Process end date first
        end_date = cls._process_end_date(end_date_param)

        # Then process start date based on end date
        start_date = cls._process_start_date(start_date_param, end_date)

        if timezone.is_naive(end_date):
            end_date = timezone.make_aware(end_date)
        if timezone.is_naive(start_date):
            start_date = timezone.make_aware(start_date)

        # Validate the resulting range
        return cls._validate_date_range(start_date, end_date)

    @classmethod
    def filter_date_range(cls, value: str) -> DateRange | None:
        preset = DateRangePresets.from_value(value)
        if not preset:
            return None
        start_date, end_date = preset.get_date_range()
        return cls._validate_date_range(start_date=start_date, end_date=end_date)

    @classmethod
    def _process_end_date(cls, end_date_param: str | datetime | None) -> datetime:
        """Processes end date with default to current time."""
        if end_date_param:
            return cls.parse_date_parameter(end_date_param)
        return timezone.now()

    @classmethod
    def _process_start_date(
        cls, start_date_param: str | datetime | None, end_date: datetime
    ) -> datetime:
        """Processes start date with default to end_date minus DEFAULT_DAYS_RANGE."""
        if start_date_param:
            return cls.parse_date_parameter(start_date_param)
        return end_date - timedelta(days=cls.DEFAULT_DAYS_RANGE)

    @classmethod
    def _validate_date_range(cls, start_date: datetime, end_date: datetime) -> DateRange:
        """Validates the date range and returns a DateRange object."""
        if start_date > timezone.now():
            raise InvalidDatetime("Start date cannot be in the future")
        if start_date > end_date:
            raise InvalidDatetime("Start date cannot be after end date")
        date_diff = end_date - start_date
        if date_diff.days > cls.MAX_DAYS_RANGE:
            raise InvalidDatetime(f"Date range cannot exceed {cls.MAX_DAYS_RANGE} days")
        if date_diff.days < 0:
            raise InvalidDatetime("Invalid date range")
        return DateRange(
            start_date=start_date,
            end_date=end_date,
        )
