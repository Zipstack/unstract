"""Tests for the source filename sent to LLMWhisperer (UN-3142).

Execution streams the document from its internal copy (``INFILE``), so the path
that reaches the adapter carries no usable name and LLMWhisperer's reports had
nothing to identify the call by. The real name travels in ``usage_kwargs``,
which every caller already populates, and is forwarded as the client's
``filename`` param.

Pins:
- ``X2Text.process`` injects the name from ``usage_kwargs``
- an explicit ``file_name`` kwarg wins over ``usage_kwargs``
- the adapter forwards it into ``WhispererRequestParams``
- ``get_whisperer_params`` emits it as ``filename``, defaulting to empty
- injecting it does not disturb the existing ``tag`` behaviour
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.adapters.x2text.constants import X2TextConstants
from unstract.sdk1.adapters.x2text.dto import (
    TextExtractionMetadata,
    TextExtractionResult,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.constants import (
    WhispererConfig,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
    LLMWhispererHelper,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.llm_whisperer_v2 import (
    LLMWhispererV2,
)
from unstract.sdk1.constants import UsageKwargs
from unstract.sdk1.file_storage import FileStorage
from unstract.sdk1.x2txt import X2Text


def _make_x2text(usage_kwargs: dict[str, Any]) -> X2Text:
    """Build an X2Text with adapter initialisation bypassed."""
    x2text = X2Text.__new__(X2Text)
    x2text._tool = MagicMock()
    x2text._usage_kwargs = usage_kwargs
    x2text._x2text_instance = MagicMock()
    x2text._x2text_instance.process.return_value = TextExtractionResult(
        extracted_text="text",
        extraction_metadata=TextExtractionMetadata(whisper_hash="h-1"),
    )
    return x2text


@pytest.fixture
def mock_fs() -> MagicMock:
    fs = MagicMock()
    fs.mime_type.return_value = "application/pdf"
    return fs


class TestX2TextInjectsSourceFilename:
    @patch.object(X2Text, "push_usage_details", MagicMock())
    def test_filename_taken_from_usage_kwargs(self, mock_fs: MagicMock) -> None:
        x2text = _make_x2text({UsageKwargs.FILE_NAME: "invoice-2024.pdf"})

        x2text.process(input_file_path="/data/exec/abc/INFILE", fs=mock_fs)

        kwargs = x2text._x2text_instance.process.call_args.kwargs
        assert kwargs[X2TextConstants.FILE_NAME] == "invoice-2024.pdf"

    @patch.object(X2Text, "push_usage_details", MagicMock())
    def test_explicit_kwarg_wins_over_usage_kwargs(self, mock_fs: MagicMock) -> None:
        """The agentic path passes the name directly rather than via usage."""
        x2text = _make_x2text({UsageKwargs.FILE_NAME: "from-usage.pdf"})

        x2text.process(
            input_file_path="/data/exec/abc/INFILE",
            fs=mock_fs,
            file_name="explicit.pdf",
        )

        kwargs = x2text._x2text_instance.process.call_args.kwargs
        assert kwargs[X2TextConstants.FILE_NAME] == "explicit.pdf"

    @patch.object(X2Text, "push_usage_details", MagicMock())
    def test_absent_usage_kwargs_yields_none(self, mock_fs: MagicMock) -> None:
        """No name available must not raise — LLMWhisperer just gets the default."""
        x2text = _make_x2text({})

        x2text.process(input_file_path="/data/exec/abc/INFILE", fs=mock_fs)

        kwargs = x2text._x2text_instance.process.call_args.kwargs
        assert kwargs[X2TextConstants.FILE_NAME] is None


class TestAdapterForwardsFilename:
    def test_process_forwards_filename_to_request_params(self) -> None:
        adapter = LLMWhispererV2(settings={})
        captured: dict[str, WhispererRequestParams] = {}

        def _capture(
            input_file_path: str,
            config: dict[str, Any],
            extra_params: WhispererRequestParams,
            fs: FileStorage | None = None,
        ) -> dict[str, Any]:
            captured["params"] = extra_params
            return {"result_text": "text", "whisper_hash": "h-1"}

        with patch.object(
            LLMWhispererHelper, "send_whisper_request", side_effect=_capture
        ):
            adapter.process(
                input_file_path="/data/exec/abc/INFILE",
                fs=MagicMock(),
                **{X2TextConstants.FILE_NAME: "statement.pdf"},
            )

        assert captured["params"].filename == "statement.pdf"


class TestWhispererParams:
    def test_filename_included_in_query_params(self) -> None:
        params = LLMWhispererHelper.get_whisperer_params(
            config={},
            extra_params=WhispererRequestParams(filename="contract.pdf"),
        )

        assert params[WhispererConfig.FILENAME] == "contract.pdf"

    def test_filename_defaults_to_empty_when_unknown(self) -> None:
        params = LLMWhispererHelper.get_whisperer_params(
            config={}, extra_params=WhispererRequestParams()
        )

        assert params[WhispererConfig.FILENAME] == ""

    def test_tag_behaviour_unchanged(self) -> None:
        """Filename must not disturb the tag, which carries customer tags."""
        params = LLMWhispererHelper.get_whisperer_params(
            config={},
            extra_params=WhispererRequestParams(tag=["customer-tag"], filename="doc.pdf"),
        )

        assert params[WhispererConfig.TAG] == "customer-tag"
        assert params[WhispererConfig.FILENAME] == "doc.pdf"
