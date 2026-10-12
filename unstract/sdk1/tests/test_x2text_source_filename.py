"""Tests for the source filename sent to LLMWhisperer (UN-3142).

Execution streams the document from its internal copy (``INFILE``), so the path
that reaches the adapter carries no usable name and LLMWhisperer's reports had
nothing to identify the call by. The real name travels in ``usage_kwargs``,
which every caller already populates, and is carried by the client's
existing ``file_name`` param.

``file_name`` must stay the only name param on the request: llmwhisperer-client
(2.8.1) rejects ``filename`` and ``file_name`` together with "use 'file_name'
only", which fails the extraction outright. An earlier revision of this change
added ``filename`` alongside it and broke every LLMWhisperer V2 extraction —
invisible here until a real call was made, because these tests mock the client.

Pins:
- ``X2Text.process`` injects the name from ``usage_kwargs``
- an explicit ``file_name`` kwarg wins over ``usage_kwargs``
- the adapter forwards it into ``WhispererRequestParams``
- ``send_whisper_request`` puts it in ``file_name``, falling back to the path name
- ``get_whisperer_params`` emits NO ``filename`` param (the collision guard)
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


def _sent_params(filename: str | None, path: str = "/data/execution/INFILE") -> dict:
    """Params as actually sent, i.e. after send_whisper_request fills file_name."""
    fs = MagicMock()
    fs.read.return_value = b"%PDF-1.4"
    with patch.object(LLMWhispererHelper, "make_request") as req:
        LLMWhispererHelper.send_whisper_request(
            input_file_path=path,
            config={},
            extra_params=WhispererRequestParams(filename=filename),
            fs=fs,
        )
    return req.call_args.kwargs["params"]


class TestSentFileName:
    """What actually goes on the wire."""

    def test_source_name_is_sent_as_file_name(self) -> None:
        params = _sent_params("invoice-2024.pdf")

        assert params[WhispererConfig.FILE_NAME] == "invoice-2024.pdf"

    def test_falls_back_to_the_path_name_when_unknown(self) -> None:
        """Pre-change behaviour: INFILE, useless but not a regression."""
        params = _sent_params(None)

        assert params[WhispererConfig.FILE_NAME] == "INFILE"

    def test_exactly_one_name_param_reaches_the_request(self) -> None:
        """The regression guard for the bug that broke every extraction."""
        params = _sent_params("invoice-2024.pdf")

        name_keys = {
            k
            for k in params
            if k in (WhispererConfig.FILE_NAME, WhispererConfig.FILENAME)
        }
        assert name_keys == {WhispererConfig.FILE_NAME}, params


class TestWhispererParams:
    def test_no_filename_param_is_ever_emitted(self) -> None:
        """The collision guard. Sending both fails the extraction outright."""
        params = LLMWhispererHelper.get_whisperer_params(
            config={},
            extra_params=WhispererRequestParams(filename="contract.pdf"),
        )

        assert WhispererConfig.FILENAME not in params

    def test_tag_behaviour_unchanged(self) -> None:
        """Filename must not disturb the tag, which carries customer tags."""
        params = LLMWhispererHelper.get_whisperer_params(
            config={},
            extra_params=WhispererRequestParams(tag=["customer-tag"], filename="doc.pdf"),
        )

        assert params[WhispererConfig.TAG] == "customer-tag"
        assert WhispererConfig.FILENAME not in params
