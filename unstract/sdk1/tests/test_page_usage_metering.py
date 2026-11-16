"""`push_usage_details` is the single point where a page-usage row is billed.

Pinned because two independent paths depend on the counts it produces and one
of them disagrees with it today (UN-4232):

* PDFs are counted by `pdfplumber`, one row per real page.
* **Everything else is counted as ONE page**, with a standing
  `TODO: Calculate page usage for other file types` at the call site.

The second is a real under-count for spreadsheets. The agentic table engine
splits an Excel workbook into *virtual* pages and extracts each one, so a
12-sheet workbook does twelve pages of work, reports twelve in the job result,
and bills one. That affects both the IDE table path
(`agentic_table/src/executor.py`) and the Agent-KV blind API
(`agentic_table/src/api_binding.py`) identically -- they share this function --
so it is a product-wide billing question, not a per-path bug, and correcting it
here moves both at once.

These tests do not assert that the current numbers are RIGHT. They assert what
they currently are, so that:

1. A change to the non-PDF count surfaces as a failing test with this
   explanation attached, instead of silently re-pricing every spreadsheet
   extraction in the product.
2. `file_name` and `run_id` keep flowing from `usage_kwargs` onto the row --
   the two fields a billing dispute is reconstructed from. The blind API
   shipped without `file_name` once already.

Excel page metering has moved twice on this branch (an over-count from blank
chunks, then this under-count), which is why it is pinned rather than
described.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from unstract.sdk1.constants import MimeType
from unstract.sdk1.x2txt import X2Text


def _x2text(usage_kwargs: dict[str, str]) -> X2Text:
    """An `X2Text` with its `__init__` bypassed.

    Constructing one for real needs a platform round-trip to resolve an adapter;
    `push_usage_details` touches only `self._tool` and `self._usage_kwargs`.
    """
    inst = object.__new__(X2Text)
    inst._usage_kwargs = usage_kwargs
    inst._tool = mock.Mock(get_env_or_die=mock.Mock(return_value="pk"))
    return inst


def _minimal_pdf(pages: int) -> bytes:
    """A structurally valid PDF with `pages` empty pages.

    Built by hand rather than with a fixture file so the page count is visible
    in the test that asserts on it. The PDF branch really does open the file
    with `pdfplumber`, so a placeholder byte string is not enough.
    """
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [{}] /Count {} >>".format(
            " ".join(f"{3 + i} 0 R" for i in range(pages)), pages
        ),
        *[
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
            for _ in range(pages)
        ],
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for n, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode()
    xref_at = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def pushed(tmp_path: Path) -> Callable[..., dict[str, Any]]:
    """Capture the single `push_page_usage_data` call as a kwargs dict."""

    def _run(
        mime_type: str,
        usage_kwargs: dict[str, str],
        *,
        pdf_pages: int = 1,
        name: str = "book.xlsx",
    ) -> dict[str, Any]:
        f = tmp_path / name
        if mime_type == MimeType.PDF:
            f.write_bytes(_minimal_pdf(pdf_pages))
        else:
            f.write_bytes(b"a real file with a real size, but not a workbook")
        with mock.patch("unstract.sdk1.x2txt.Audit") as m_audit:
            _x2text(usage_kwargs).push_usage_details(str(f), mime_type)
        assert m_audit.return_value.push_page_usage_data.call_count == 1
        return m_audit.return_value.push_page_usage_data.call_args.kwargs

    return _run


def test_a_pdf_is_billed_per_real_page(pushed: Callable[..., dict[str, Any]]) -> None:
    """The contrast that makes the spreadsheet case a gap rather than a policy.

    PDFs are counted by `pdfplumber`, so pages of work and pages billed agree.
    """
    call = pushed(MimeType.PDF, {"run_id": "job-1"}, pdf_pages=3, name="rent-roll.pdf")

    assert call["page_count"] == 3


def test_a_spreadsheet_is_billed_as_a_single_page(
    pushed: Callable[..., dict[str, Any]],
) -> None:
    """The under-count, pinned with its consequence spelled out.

    If this starts failing because the count became sheet- or virtual-page
    aware, that is an INTENTIONAL billing change: update this test, and check
    that `agentic_table`'s reported `pages` now agrees with it (the job result
    and the usage row currently disagree for Excel).
    """
    call = pushed(XLSX_MIME, {"run_id": "job-1", "file_name": "book.xlsx"})

    assert call["page_count"] == 1, (
        "non-PDF inputs are metered as one page regardless of how many pages "
        "of work they cause; the table engine splits a workbook into virtual "
        "pages and bills this single row for all of them"
    )


def test_the_billing_identifiers_reach_the_row(
    pushed: Callable[..., dict[str, Any]],
) -> None:
    """`run_id` and `file_name` are carried only by `usage_kwargs`.

    `Audit.push_page_usage_data` reads both off that dict and defaults each to
    `""`, so a caller that omits one gets a billed row with no way back to the
    job or the input. The Agent-KV blind API omitted `file_name` on its first
    cut (UN-4232); nothing failed, which is why this exists.
    """
    call = pushed(XLSX_MIME, {"run_id": "job-7", "file_name": "rent-roll.xlsx"})

    assert call["kwargs"]["run_id"] == "job-7"
    assert call["kwargs"]["file_name"] == "rent-roll.xlsx"


def test_a_missing_file_name_is_not_rejected_here(
    pushed: Callable[..., dict[str, Any]],
) -> None:
    """Documents WHY the omission was silent: this layer tolerates it.

    Not an endorsement -- the point is that no exception, no warning and no log
    marks the gap, so the only defence is the caller passing the field. Both
    table paths now do.
    """
    call = pushed(XLSX_MIME, {"run_id": "job-7"})

    assert call["kwargs"].get("file_name") is None
