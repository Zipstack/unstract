"""Strict page-range resolver for image output mode (mirror of LLMWhisperer's)."""

import pytest
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.page_range import (
    PageRangeError,
    normalize_page_range,
    resolve_page_range,
)


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("", ""), ("   ", ""), (" 1-3 , 7 ", "1-3,7"), ("-5", "-5"), ("4-", "4-")],
)
def test_normalize_canonicalises(spec: str, expected: str) -> None:
    """Whitespace is removed; empty means every page."""
    assert normalize_page_range(spec) == expected


@pytest.mark.parametrize("spec", ["abc", "1--2", "1-2-3", ",", "-", "1,,2", "1 2"])
def test_normalize_rejects_malformed(spec: str) -> None:
    """A token that is not a page or range is a syntax error."""
    with pytest.raises(PageRangeError):
        normalize_page_range(spec)


@pytest.mark.parametrize(
    ("spec", "page_count", "expected"),
    [
        ("", 3, [1, 2, 3]),
        ("2", 3, [2]),
        ("1-10", 5, [1, 2, 3, 4, 5]),
        ("3,7", 5, [3]),
        ("-2", 5, [1, 2]),
        ("4-", 5, [4, 5]),
        ("3,1,3", 5, [1, 3]),
        ("2-4,3-5", 5, [2, 3, 4, 5]),
    ],
)
def test_resolve(spec: str, page_count: int, expected: list[int]) -> None:
    """Past-end pages drop; the result is sorted and deduplicated."""
    assert resolve_page_range(spec, page_count) == expected


@pytest.mark.parametrize("spec", ["0", "0-2", "5-3", "-0"])
def test_resolve_rejects_zero_and_reversed(spec: str) -> None:
    """Page 0 and a reversed range are typos, not silent widenings."""
    with pytest.raises(PageRangeError):
        resolve_page_range(spec, 5)


@pytest.mark.parametrize("spec", ["7", "10-20", "6-"])
def test_resolve_rejects_empty_selection(spec: str) -> None:
    """A selection with no page left names the document size."""
    with pytest.raises(PageRangeError) as excinfo:
        resolve_page_range(spec, 5)
    assert "5-page" in str(excinfo.value)


def test_page_range_error_is_value_error() -> None:
    """Existing ValueError handlers keep catching it."""
    assert issubclass(PageRangeError, ValueError)


@pytest.mark.parametrize(
    "spec",
    ["1" + "0" * 5000, "1234567", ",".join(["1"] * 600)],
    ids=["huge-number", "seven-digits", "too-long"],
)
def test_normalize_rejects_oversized_values(spec: str) -> None:
    """Huge numbers or values are a PageRangeError, never a bare int() ValueError."""
    with pytest.raises(PageRangeError):
        normalize_page_range(spec)
