"""Strict ``pages_to_extract`` resolver for image output mode.

A copy of LLMWhisperer's ``backend/app/util/page_range.py`` (LW-473), which
resolves the same setting for ``/pdf-to-images``. The SDK uses it to count
the selected pages BEFORE submitting, so the page-budget check and an invalid
range fail before anything is converted or billed. The two copies must stay
identical in behaviour: same grammar as /whisper (``1-5,7,10-,-3``), page 0,
reversed ranges and empty selections rejected, pages past the end dropped,
the result deduplicated and ascending.
"""

import re

# Page numbers have at most 6 digits and the whole value at most 1000
# characters: a value is stored in status metadata and in a Redis key, and a
# huge digit run would make int() raise a bare ValueError (4300-digit limit).
# ASCII digits only: ``\d`` would accept other scripts' digits ("１-３").
_TOKEN_RE = re.compile(r"^([0-9]{1,6}-([0-9]{1,6})?|-[0-9]{1,6}|[0-9]{1,6})$")
MAX_SPEC_LENGTH = 1000


class PageRangeError(ValueError):
    """``pages_to_extract`` is malformed or selects no valid page."""


class PageLimitError(PageRangeError):
    """The selection has more pages than the caller's ``max_pages``."""

    def __init__(self, selected: int, max_pages: int) -> None:
        """Record the selected count and the limit it exceeds."""
        self.selected = selected
        self.max_pages = max_pages
        super().__init__(
            f"{selected} pages to convert, maximum supported is {max_pages}. "
            "Please split the document into smaller parts or select fewer "
            "pages with pages_to_extract."
        )


def normalize_page_range(spec: str) -> str:
    """Return the canonical form of ``spec`` (whitespace removed).

    Syntax only; no page count is needed. ``""`` means every page.

    Raises:
        PageRangeError: A token is not ``a``, ``a-b``, ``a-`` or ``-b``.
    """
    spec = spec or ""
    # Whitespace between digits ("1 2") would collapse into a different page.
    if re.search(r"[0-9]\s+[0-9]", spec):
        raise PageRangeError(f"invalid page range '{spec}'")
    compact = re.sub(r"\s+", "", spec)
    if not compact:
        return ""
    if len(compact) > MAX_SPEC_LENGTH:
        raise PageRangeError(
            f"invalid page range: longer than {MAX_SPEC_LENGTH} characters"
        )
    for token in compact.split(","):
        if not _TOKEN_RE.match(token):
            raise PageRangeError(
                f"invalid page range '{spec}': '{token}' is not a page (7), "
                "a range (1-5), or an open range (10- or -3) of pages up to "
                "999999"
            )
    return compact


def validate_page_range(spec: str) -> str:
    """Check ``spec`` without a page count; return its canonical form.

    Rejects what is wrong for any document: bad syntax, page 0 and a reversed
    range. A selection past the end can only be found by
    ``resolve_page_range``.

    Raises:
        PageRangeError: Malformed, page 0 or a reversed range.
    """
    canonical = normalize_page_range(spec)
    _token_ranges(spec, canonical, None)
    return canonical


def resolve_page_range(
    spec: str, page_count: int, max_pages: int | None = None
) -> list[int]:
    """Resolve ``spec`` against a document of ``page_count`` pages.

    Args:
        spec: The ``pages_to_extract`` value; ``""`` selects every page.
        page_count: Pages in the document.
        max_pages: Optional limit on the selected count, checked before the
            page list is built, so a document claiming millions of pages does
            not allocate them.

    Returns:
        The selected 1-based page numbers, ascending, without duplicates.

    Raises:
        PageLimitError: More than ``max_pages`` pages are selected.
        PageRangeError: Malformed, page 0, a reversed range, or no page left.
    """
    canonical = normalize_page_range(spec)
    if not canonical:
        ranges = [(1, page_count)]
    else:
        ranges = [
            (start, min(end, page_count))
            for start, end in _token_ranges(spec, canonical, page_count)
        ]
    merged = _merge_ranges(ranges)
    selected = sum(end - start + 1 for start, end in merged)
    if not selected:
        raise PageRangeError(
            f"page range '{spec}' selects no pages of this {page_count}-page document"
        )
    if max_pages is not None and selected > max_pages:
        raise PageLimitError(selected, max_pages)
    return [page for start, end in merged for page in range(start, end + 1)]


def _token_ranges(
    spec: str, canonical: str, page_count: int | None
) -> list[tuple[int, int]]:
    """Inclusive ``(start, end)`` per token of a canonical, non-empty value.

    An open end (``10-``) is ``page_count``, or ``start`` when the count is
    unknown (only the bounds are being checked then).

    Raises:
        PageRangeError: Page 0 or a reversed range.
    """
    ranges: list[tuple[int, int]] = []
    for token in filter(None, canonical.split(",")):
        if token.startswith("-"):
            start, end = 1, int(token[1:])
        elif token.endswith("-"):
            start = int(token[:-1])
            end = page_count if page_count is not None else start
        elif "-" in token:
            start_text, end_text = token.split("-")
            start, end = int(start_text), int(end_text)
            if start > end:
                raise PageRangeError(
                    f"invalid page range '{spec}': '{token}' is reversed"
                )
        else:
            start = end = int(token)
        if start < 1 or end < 1:
            raise PageRangeError(f"invalid page range '{spec}': page numbers start at 1")
        ranges.append((start, end))
    return ranges


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Sort inclusive ranges and merge overlapping or adjacent ones; drop empties."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(r for r in ranges if r[0] <= r[1]):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
