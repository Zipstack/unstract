"""Tests for the LLMWhisperer V2 adapter's query params and page-range billing.

Both read the same ``pages_to_extract`` setting: the adapter sends it to the
service, and ``X2Text`` bills for the pages it selects.
"""

import pytest
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import LLMWhispererHelper
from unstract.sdk1.constants import MimeType
from unstract.sdk1.x2txt import X2Text


def _params(config: dict) -> dict:
    return LLMWhispererHelper.get_whisperer_params(
        config=config, extra_params=WhispererRequestParams()
    )


def test_line_splitter_strategy_from_config() -> None:
    """The key stored by the adapter's JSON schema is the one that is read."""
    params = _params({"line_splitter_strategy": "right-priority"})

    assert params["line_splitter_strategy"] == "right-priority"


@pytest.mark.parametrize("strategy", ["left-priority", "mid-priority", "right-priority"])
def test_supported_line_splitter_strategies_pass_through(strategy: str) -> None:
    """Every value the service accepts reaches it unchanged."""
    params = _params({"line_splitter_strategy": strategy})

    assert params["line_splitter_strategy"] == strategy


@pytest.mark.parametrize(
    "stored", ["", "  ", "left_priority", "LEFT-PRIORITY", "nonsense"]
)
def test_unsupported_line_splitter_strategy_falls_back(
    stored: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A stored value the service would reject keeps the previous behaviour."""
    params = _params({"line_splitter_strategy": stored})

    assert params["line_splitter_strategy"] == "left-priority"
    assert "Unsupported line splitter strategy" in caplog.text


def test_page_separator_read_under_legacy_config_key() -> None:
    """Existing configs store the misspelled key but the client kwarg is correct."""
    params = _params({"page_seperator": "<<< {{page_no}} >>>"})

    assert params["page_separator"] == "<<< {{page_no}} >>>"
    assert "page_seperator" not in params


class _FakeAdapter:
    """Stands in for the adapter instance, which only needs ``.config`` here."""

    def __init__(self, config: dict | None) -> None:
        self.config = config


def _billable(config: dict | None, page_count: int) -> int:
    """Run ``_get_billable_page_count`` against a stub adapter.

    ``X2Text.__init__`` requires a live ``BaseTool``, and the method under test
    reads nothing but ``self._x2text_instance.config``.
    """
    x2text = X2Text.__new__(X2Text)
    x2text._x2text_instance = _FakeAdapter(config) if config is not None else None
    return x2text._get_billable_page_count(page_count)


@pytest.mark.parametrize(
    ("spec", "total_pages", "expected"),
    [
        ("1,3,5", 10, 3),
        ("2-4", 10, 3),
        ("50-", 60, 11),  # open-ended range runs to the last page
        ("1-3,2-4", 10, 4),  # overlapping ranges are counted once
        ("0-3", 10, 3),  # pages are 1-indexed; page 0 does not exist
        ("1-999", 10, 10),  # clamped to the document length
        ("99", 10, 0),  # a single out-of-range page selects nothing
        ("5-2", 10, 0),  # an inverted range selects nothing
    ],
)
def test_parse_pages_to_extract_counts_selected_pages(
    spec: str, total_pages: int, expected: int
) -> None:
    """UN-3038: billing follows the pages the adapter actually extracts."""
    assert X2Text._parse_pages_to_extract(spec, total_pages) == expected


def test_billable_page_count_narrows_to_the_selected_range() -> None:
    """The whole point of UN-3038: 3 pages of a 100-page document bill as 3."""
    assert _billable({"pages_to_extract": "2-4"}, 100) == 3


@pytest.mark.parametrize(
    "config",
    [
        {"pages_to_extract": ""},  # setting present but empty
        {"pages_to_extract": "   "},  # whitespace only
        {"pages_to_extract": "not-a-range"},  # unparseable
        {"pages_to_extract": "99"},  # parses, but selects nothing
        {},  # setting absent
        None,  # no adapter instance at all
    ],
)
def test_billable_page_count_falls_back_to_the_full_count(config: dict | None) -> None:
    """Usage must never be UNDER-reported because a setting was malformed.

    Each of these makes the page selection unusable; billing then falls back to
    every page in the document rather than to zero.
    """
    assert _billable(config, 10) == 10


def test_push_usage_details_reports_the_narrowed_page_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The narrowing must be wired into the value Audit actually receives.

    Asserting on ``_get_billable_page_count`` alone would still pass if the
    call were dropped from ``push_usage_details``, which is the only place the
    number becomes a bill.
    """
    import unstract.sdk1.x2txt as x2txt_module

    recorded: dict[str, int] = {}

    class _FakeAudit:
        def push_page_usage_data(self, **kwargs: object) -> None:
            recorded["page_count"] = kwargs["page_count"]

    class _FakePdf:
        pages = [object()] * 100

        def __enter__(self) -> "_FakePdf":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(x2txt_module, "Audit", _FakeAudit)
    monkeypatch.setattr(x2txt_module.pdfplumber, "open", lambda _: _FakePdf())
    monkeypatch.setattr(
        x2txt_module.ToolUtils, "get_file_size", staticmethod(lambda *a, **k: 1024)
    )

    class _FakeFs:
        def read(self, **kwargs: object) -> bytes:
            return b"%PDF-1.4"

    class _FakeTool:
        def get_env_or_die(self, key: str) -> str:
            return "test-key"

    x2text = X2Text.__new__(X2Text)
    x2text._x2text_instance = _FakeAdapter({"pages_to_extract": "2-4"})
    x2text._tool = _FakeTool()
    x2text._usage_kwargs = {}

    x2text.push_usage_details("doc.pdf", MimeType.PDF, fs=_FakeFs())

    # 100-page document, 3 pages extracted -> 3 pages billed.
    assert recorded["page_count"] == 3
