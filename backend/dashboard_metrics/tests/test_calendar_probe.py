"""Probe: run the clock-sensitive suites at the boundaries that used to break them."""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from dashboard_metrics.tests.test_tasks import (
    TestMonthlyMatchesTheOldDerivation,
    TestMonthlyThroughTheTask,
    TestSourceWindow,
)

_BOUNDARIES = [
    datetime(2026, 10, 1, 0, 0, 0, 100000, tzinfo=dt_timezone.utc),   # 1st of a month
    datetime(2026, 3, 31, 23, 59, 59, 900000, tzinfo=dt_timezone.utc),  # month end, pre-midnight
]


def _at(when):
    def _factory(cls):
        class _Frozen(cls):
            def setUp(self):
                with patch("django.utils.timezone.now", return_value=when):
                    super().setUp()
                self.now = when
        _Frozen.__name__ = f"{cls.__name__}At{when:%Y%m%d%H%M}"
        _Frozen.__qualname__ = _Frozen.__name__
        return _Frozen
    return _factory


for _when in _BOUNDARIES:
    for _cls in (TestSourceWindow, TestMonthlyThroughTheTask, TestMonthlyMatchesTheOldDerivation):
        _frozen = _at(_when)(_cls)
        globals()[_frozen.__name__] = _frozen
