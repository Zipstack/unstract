"""Per-word OCR confidence reaching `TextExtractionMetadata`.

**Where the fixtures come from.** Every shape asserted here was read out of the
LLMWhisperer service's own source rather than guessed or copied from a sample
response, because the published API docs do not describe either shape:

* `confidence_metadata` -- `backend/tasks_v2.py`, which builds one
  `confidence_metadata_row` per line of `result_text`, appends
  `{"text": ..., "confidence": ...}` per word, and assigns the assembled list
  to `assembled_document["confidence_metadata"]`. `/whisper-retrieve` returns
  that whole assembled document, and the client wraps it as `extraction`,
  which `LLMWhispererHelper.make_request` unwraps and returns -- so it arrives
  at the adapter as a plain top-level key.
* `line_confidence` -- `backend/app/controller/controller_v2.py`'s
  `_create_metadata_dict`, which adds the key to a `/highlights` entry only
  when the stored row has a fifth element, i.e. only when the whisper request
  carried `include_line_confidence=true`. The adapter sets that flag from
  `enable_highlight`, so the two travel together.

The service reports `confidence_metadata` on every `layout_preserving`
retrieve whether or not the caller asked for highlighting, so the gate under
test is the ADAPTER's, not the service's: it scales with the document's word
count and no caller that did not ask for it should carry it in memory.
"""

from _pytest.monkeypatch import MonkeyPatch
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.helper import (
    LLMWhispererHelper,
)
from unstract.sdk1.adapters.x2text.llm_whisperer_v2.src.llm_whisperer_v2 import (
    LLMWhispererV2,
)

_BASE_CONFIG = {"url": "https://svc.example.com", "unstract_key": "key"}

#: One entry per line of `result_text`; a line the OCR gave no word detail for
#: is an empty list, which is what keeps the outer list index-aligned.
_CONFIDENCE_METADATA = [
    [],
    [
        {"text": "Invoice", "confidence": 0.98},
        {"text": "Total", "confidence": 0.91},
    ],
    [{"text": "1,240.00", "confidence": 0.74}],
]

#: A `/highlights` entry as `_create_metadata_dict` builds it with the fifth
#: `raw` element present. `base_y_percent`/`height_percent` are part of the
#: real shape and are kept so this does not quietly become a narrower fixture
#: than the service sends.
#:
#: **Keyed from "0", because the endpoint is 0-indexed.** It returns
#: `{i: ... for i, lx in enumerate(line_metadata)}`, so the first line of the
#: document is key "0" while the line numbers embedded in the text and cited by
#: the model are 1-indexed. Every consumer converts between the two; a fixture
#: keyed from "1" here reads as though the producer were 1-indexed, which would
#: put every coordinate out by exactly one line.
_LINE_METADATA = {
    "0": {
        "raw": [0, 155, 51, 3168, 0.93],
        "page": 0,
        "page_height": 3168,
        "base_y": 155,
        "height": 51,
        "base_y_percent": 4.8927,
        "height_percent": 1.6098,
        "line_confidence": 0.93,
    }
}


def _adapter(**overrides: object) -> LLMWhispererV2:
    return LLMWhispererV2({**_BASE_CONFIG, **overrides})


def _stub(monkeypatch: MonkeyPatch, response: dict) -> None:
    monkeypatch.setattr(LLMWhispererHelper, "send_whisper_request", lambda **_: response)
    monkeypatch.setattr(
        LLMWhispererHelper, "extract_text_from_response", lambda *_a, **_k: "text"
    )


def _response() -> dict:
    return {
        "whisper_hash": "wh1",
        "line_metadata": _LINE_METADATA,
        "confidence_metadata": _CONFIDENCE_METADATA,
    }


class TestGatedOnHighlight:
    def test_requested_highlight_carries_the_word_confidence(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        _stub(monkeypatch, _response())

        meta = _adapter().process("in.pdf", enable_highlight=True).extraction_metadata

        assert meta.confidence_metadata == _CONFIDENCE_METADATA
        # Index-aligned with the text's lines, empty list and all: a consumer
        # indexes into it directly, so a filtered-out blank line would shift
        # every confidence value after it onto the wrong row.
        assert meta.confidence_metadata[0] == []
        assert meta.confidence_metadata[1][0]["text"] == "Invoice"

    def test_no_highlight_requested_drops_it_even_when_the_service_sends_it(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # The service does not gate this key, so the response carries it; the
        # adapter must not. This is the whole reason the field is not simply
        # assigned through.
        _stub(monkeypatch, _response())

        meta = _adapter().process("in.pdf").extraction_metadata

        assert meta.confidence_metadata is None

    def test_highlight_requested_but_service_sent_none(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        # A non-`layout_preserving` mode, or an OCR pass that produced no word
        # detail at all: absent rather than empty, so a consumer can tell "not
        # reported" from "reported as nothing".
        _stub(monkeypatch, {"whisper_hash": "wh1", "line_metadata": _LINE_METADATA})

        meta = _adapter().process("in.pdf", enable_highlight=True).extraction_metadata

        assert meta.confidence_metadata is None


class TestLineConfidenceRidesWithHighlight:
    def test_line_confidence_is_inside_the_line_metadata_entry(
        self, monkeypatch: MonkeyPatch
    ) -> None:
        """Pins WHERE per-line confidence lives, which is easy to get wrong.

        It is not a sibling of `line_metadata` and not a separate fetch: the
        service folds it into each `/highlights` entry, so a consumer that
        already walks `line_metadata` for geometry gets it for free. The
        agentic extractors depend on that -- it is why asking for per-line
        confidence costs no additional call.
        """
        _stub(monkeypatch, _response())

        meta = _adapter().process("in.pdf", enable_highlight=True).extraction_metadata

        entry = meta.line_metadata["0"]
        assert entry["line_confidence"] == 0.93
        # Also the fifth element of `raw`, which is where the service reads it
        # from. Both are asserted because the engine reads the named keys while
        # `raw` is what the IDE's viewer consumes.
        assert entry["raw"][4] == 0.93
