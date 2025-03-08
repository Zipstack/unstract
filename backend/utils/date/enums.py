from datetime import timedelta
from enum import Enum

from django.utils import timezone
from utils.date.exceptions import InvalidDateRange


class DateRangePresets(Enum):
    """Represents relative time presets.

    Can be used for filtering entities
    """

    TODAY = ("today", 0, "Today")
    YESTERDAY = ("yesterday", 1, "Yesterday")
    LAST_7_DAYS = ("last_7_days", 7, "Last 7 Days")
    LAST_30_DAYS = ("last_30_days", 30, "Last 30 Days")

    def __init__(self, key: str, days: int, display_name: str):
        self.key = key
        self.days = days
        self.display_name = display_name

    def get_start_date(self):
        return timezone.now() - timedelta(days=self.days)

    def get_end_date(self):
        return timezone.now()

    def get_date_range(self):
        return self.get_start_date(), self.get_end_date()

    @classmethod
    def from_value(cls, value: str):
        try:
            return next(preset for preset in cls if preset.key == value)
        except StopIteration:
            valid_values = [preset.key for preset in cls]
            raise InvalidDateRange(
                f"Invalid date range value: '{value}'. "
                f"Valid values are: {', '.join(valid_values)}"
            )

    @classmethod
    def choices(cls):
        return [(preset.key, preset.display_name) for preset in cls]
