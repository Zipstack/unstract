"""Tests for the query params the LLMWhisperer V2 adapter sends."""

import pytest

from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import LLMWhispererHelper


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
