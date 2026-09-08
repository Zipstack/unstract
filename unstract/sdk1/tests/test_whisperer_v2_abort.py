"""LLMWhisperer v2 extraction is abortable, and its result shape is unchanged.

Extraction is where a document run most often wedges: a large PDF can sit in
LLMWhisperer for up to fifteen minutes, and until now a user pressing Stop had
to wait it out.

The client's own wait loop cannot tell us to stop, so we drive the polling
ourselves. That means reproducing the exact dict the vendored loop returns —
``ExtractorError`` is built from ``status_code`` and ``message`` at the call
site, so a drift there turns a clear failure into a confusing one. The first
class below pins that contract; the second pins the new behaviour.

Note the honest limit: LLMWhisperer exposes no cancel endpoint, so an
abandoned extraction still runs, and is still billed, on their side. What we
buy is the worker and the user not waiting for it.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from unstract.sdk1.adapters.exceptions import ExtractorError
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.dto import (
    WhispererRequestParams,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
    LLMWhispererHelper,
)
from unstract.sdk1.utils.aborting import AbortedError, abort_scope

_CONFIG = {
    "url": "https://llmwhisperer.example.com",
    "unstract_key": "test-key",
}


def _client_returning(
    *, accept: dict, statuses: list[dict], retrieve: dict | None = None
) -> MagicMock:
    """A stand-in LLMWhispererClientV2.

    `accept` is the initial whisper() response; `statuses` are served one per
    poll, the last repeating forever.
    """
    client = MagicMock()
    client.whisper.return_value = accept
    seen = {"n": 0}

    def _status(**_kwargs: object) -> dict:
        idx = min(seen["n"], len(statuses) - 1)
        seen["n"] += 1
        return statuses[idx]

    client.whisper_status.side_effect = _status
    client.whisper_retrieve.return_value = retrieve or {
        "status_code": 200,
        "extraction": {"result_text": "page one"},
    }
    return client


_ACCEPTED = {"status_code": 202, "whisper_hash": "hash-1", "message": "accepted"}


class TestResultShapeIsUnchanged:
    """These pin the contract the call site depends on."""

    def test_a_completed_extraction_returns_the_extraction_payload(self) -> None:
        client = _client_returning(
            accept=_ACCEPTED, statuses=[{"status_code": 200, "status": "processed"}]
        )
        with patch(
            "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
            "LLMWhispererClientV2",
            return_value=client,
        ):
            result = LLMWhispererHelper.make_request(config=_CONFIG, params={}, data=b"x")

        assert result["result_text"] == "page one"
        # The hash is stitched into the returned extraction for downstream use.
        assert result["whisper_hash"] == "hash-1"

    def test_a_failed_status_becomes_an_extractor_error(self) -> None:
        client = _client_returning(
            accept=_ACCEPTED,
            statuses=[{"status_code": 200, "status": "error", "message": "bad pdf"}],
        )
        with (
            patch(
                "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
                "LLMWhispererClientV2",
                return_value=client,
            ),
            pytest.raises(ExtractorError) as exc,
        ):
            LLMWhispererHelper.make_request(config=_CONFIG, params={}, data=b"x")

        assert "bad pdf" in str(exc.value)

    def test_an_unreachable_status_call_becomes_an_extractor_error(self) -> None:
        client = _client_returning(
            accept=_ACCEPTED, statuses=[{"status_code": 500, "status": "unknown"}]
        )
        with (
            patch(
                "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
                "LLMWhispererClientV2",
                return_value=client,
            ),
            pytest.raises(ExtractorError),
        ):
            LLMWhispererHelper.make_request(config=_CONFIG, params={}, data=b"x")

    def test_a_synchronous_200_still_works(self) -> None:
        """Small documents come back on the first response, with no polling."""
        client = _client_returning(
            accept={
                "status_code": 200,
                "whisper_hash": "hash-2",
                "extraction": {"result_text": "short doc"},
            },
            statuses=[],
        )
        with patch(
            "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
            "LLMWhispererClientV2",
            return_value=client,
        ):
            result = LLMWhispererHelper.make_request(config=_CONFIG, params={}, data=b"x")

        assert result["result_text"] == "short doc"
        client.whisper_status.assert_not_called()


class TestAbort:
    def test_a_long_extraction_is_abandoned_promptly(self) -> None:
        """The case this exists for: a big PDF and an impatient user."""
        client = _client_returning(
            accept=_ACCEPTED,
            statuses=[{"status_code": 200, "status": "processing"}],  # forever
        )
        started = time.monotonic()
        with (
            patch(
                "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
                "LLMWhispererClientV2",
                return_value=client,
            ),
            abort_scope(lambda: True),
            pytest.raises(AbortedError),
        ):
            LLMWhispererHelper.make_request(config=_CONFIG, params={}, data=b"x")

        assert time.monotonic() - started < 5

    def test_without_an_abort_the_poll_loop_runs_to_completion(self) -> None:
        client = _client_returning(
            accept=_ACCEPTED,
            statuses=[
                {"status_code": 200, "status": "processing"},
                {"status_code": 200, "status": "processed"},
            ],
        )
        with (
            patch(
                "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
                "LLMWhispererClientV2",
                return_value=client,
            ),
            patch(
                "unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper."
                "WhispererDefaults.POLL_INTERVAL",
                0.01,
            ),
            abort_scope(lambda: False),
        ):
            result = LLMWhispererHelper.make_request(config=_CONFIG, params={}, data=b"x")

        assert result["result_text"] == "page one"

    def test_we_do_not_ask_the_client_to_wait_for_us(self) -> None:
        """The client's own loop is uninterruptible, so we must drive it."""
        params = LLMWhispererHelper.get_whisperer_params(
            config=_CONFIG, extra_params=WhispererRequestParams()
        )

        assert params["wait_for_completion"] is False
