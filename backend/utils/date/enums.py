from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from django.utils import timezone

from utils.date.exceptions import InvalidDateRange


class DateRangePresets(Enum):
    """Represents relative time presets.

    Can be used for filtering entities
    """

    TODAY = ("today", 0, "Today")
    YESTERDAY = ("yesterday", 1, "Yesterday")
    LAST_2_DAYS = ("last_2_days", 2, "Last 2 Days")
    LAST_7_DAYS = ("last_7_days", 7, "Last 7 Days")
    LAST_30_DAYS = ("last_30_days", 30, "Last 30 Days")

    def __init__(self, key: str, days: int, display_name: str):
        self.key = key
        self.days = days
        self.display_name = display_name

    def get_start_date(self) -> datetime:
        now = timezone.now()
        if self == DateRangePresets.TODAY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif self == DateRangePresets.YESTERDAY:
            return (now - timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        return now - timedelta(days=self.days)

    def get_end_date(self) -> datetime:
        now = timezone.now()
        if self == DateRangePresets.YESTERDAY:
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        return now

    def get_date_range(self) -> tuple[datetime, datetime]:
        return self.get_start_date(), self.get_end_date()

    @classmethod
    def from_value(cls, value: str) -> DateRangePresets | None:
        try:
            return next(preset for preset in cls if preset.key == value)
        except StopIteration as e:
            valid_values = [preset.key for preset in cls]
            raise InvalidDateRange(
                f"Invalid date range value: '{value}'. "
                f"Valid values are: {', '.join(valid_values)}"
            ) from e

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(preset.key, preset.display_name) for preset in cls]
