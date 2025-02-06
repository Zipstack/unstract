import datetime
from dataclasses import dataclass


@dataclass
class DateRange:
    """
    Represents a validated date range with start and end dates.

    Attributes:
        start_date: Beginning of the date range
        end_date: End of the date range
    """

    start_date: datetime
    end_date: datetime
