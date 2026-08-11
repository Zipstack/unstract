"""Tests for the query params the LLMWhisperer V2 adapter sends."""

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


def test_page_separator_read_under_legacy_config_key() -> None:
    """Existing configs store the misspelled key but the client kwarg is correct."""
    params = _params({"page_seperator": "<<< {{page_no}} >>>"})

    assert params["page_separator"] == "<<< {{page_no}} >>>"
    assert "page_seperator" not in params
