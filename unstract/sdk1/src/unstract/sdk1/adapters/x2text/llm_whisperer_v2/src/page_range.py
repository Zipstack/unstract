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
_TOKEN_RE = re.compile(r"^(\d{1,6}-(\d{1,6})?|-\d{1,6}|\d{1,6})$")
MAX_SPEC_LENGTH = 1000


class PageRangeError(ValueError):
    """``pages_to_extract`` is malformed or selects no valid page."""


def normalize_page_range(spec: str) -> str:
    """Return the canonical form of ``spec`` (whitespace removed).

    Syntax only; no page count is needed. ``""`` means every page.

    Raises:
        PageRangeError: A token is not ``a``, ``a-b``, ``a-`` or ``-b``.
    """
    spec = spec or ""
    # Whitespace between digits ("1 2") would collapse into a different page.
    if re.search(r"\d\s+\d", spec):
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


def resolve_page_range(spec: str, page_count: int) -> list[int]:
    """Resolve ``spec`` against a document of ``page_count`` pages.

    Returns:
        The selected 1-based page numbers, ascending, without duplicates.

    Raises:
        PageRangeError: Malformed, page 0, a reversed range, or no page left.
    """
    canonical = normalize_page_range(spec)
    if not canonical:
        pages = set(range(1, page_count + 1))
    else:
        pages = set()
        for token in canonical.split(","):
            if token.startswith("-"):
                start, end = 1, int(token[1:])
            elif token.endswith("-"):
                start, end = int(token[:-1]), page_count
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
                raise PageRangeError(
                    f"invalid page range '{spec}': page numbers start at 1"
                )
            pages.update(range(start, min(end, page_count) + 1))
    if not pages:
        raise PageRangeError(
            f"page range '{spec}' selects no pages of this {page_count}-page document"
        )
    return sorted(pages)
