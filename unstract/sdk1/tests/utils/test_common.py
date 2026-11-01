"""Unit tests for unstract.sdk1.utils.common."""

import pytest

from unstract.sdk1.utils.common import Utils


@pytest.mark.parametrize(
    ("num", "expected"),
    [
        (0, "0.00 B"),
        (1023, "1023.00 B"),
        (1024, "1.00 KB"),
        (1024**4, "1.00 TB"),
        (1024**5, "1.00 PB"),
        (3 * 1024**5, "3.00 PB"),
    ],
)
def test_pretty_file_size(num: float, expected: str) -> None:
    assert Utils.pretty_file_size(num) == expected
