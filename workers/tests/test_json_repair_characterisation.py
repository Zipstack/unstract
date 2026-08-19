"""Characterisation + contract tests for ``json_repair_helper`` (UN-4017).

Part 1 pins the legacy parser against a frozen copy of the implementation
as it stood before UN-4017. The repair logic accumulated two years of
observed LLM edge cases, so the safe way to extend it is to prove the old
path is bit-for-bit unchanged and add new behaviour behind an opt-in
contract. If a future edit to ``_repair_legacy`` changes any result here,
these tests fail — that is the point.

Part 2 covers the opt-in contract path: the shapes that reached
``output_manager_helper.handle_prompt_output_update`` as a list and 500'd
the backend.
"""

import json
import logging

import pytest
from executor.executors.json_repair_helper import (
    JsonContract,
    _raw_debug_enabled,
    _skeleton,
    repair_json_with_best_structure,
)

# --- Frozen reference: the implementation prior to UN-4017 -------------
# Do not "clean up" or re-sync this with the production function. Its only
# job is to be the historical behaviour that production must still match.


def _original_impl(json_str):
    try:
        return json.loads(json_str)
    except ValueError:
        pass

    try:
        from json_repair import repair_json

        parsed_as_is = repair_json(
            json_str=json_str, return_objects=True, ensure_ascii=False
        )
        parsed_with_wrap = repair_json(
            json_str="[" + json_str, return_objects=True, ensure_ascii=False
        )

        if isinstance(parsed_as_is, str) and isinstance(parsed_with_wrap, str):
            return parsed_as_is
        if isinstance(parsed_as_is, str):
            return parsed_with_wrap
        if isinstance(parsed_with_wrap, str):
            return parsed_as_is

        if (
            isinstance(parsed_with_wrap, list)
            and len(parsed_with_wrap) == 1
            and parsed_with_wrap[0] == parsed_as_is
        ):
            return parsed_as_is

        if isinstance(parsed_as_is, (dict, list)):
            if isinstance(parsed_with_wrap, list) and len(parsed_with_wrap) > 1:
                return parsed_with_wrap
            else:
                return parsed_as_is

        return parsed_with_wrap
    except ImportError:
        return json_str


OBJ = '{"invoice_number": "INV-001", "total": 1250.5}'
LONG = (
    '{"invoice_number": "INV-001", "vendor": "Acme Ltd", "total": 1250.5, '
    '"line_items": [{"desc": "Widget", "qty": 2}, {"desc": "Gadget", "qty": 7}]}'
)

# Highlight / confidence / line-number responses. The `// 0x..` comment after
# each value is mapped onto the parsed structure positionally, so the shape
# returned here must correspond 1:1 with the comment stream.
ANNOTATED = '{\n  "invoice_number": "INV-001", // 0x1a2b\n  "total": 1250.5 // 0x3c4d\n}'
WORD_CONF = OBJ + "\n%%%\nINV-001 0.98 1250.5 0.91\n%%%"
ANNOTATED_AND_WORD_CONF = ANNOTATED + "\n%%%\nINV-001 0.98\n%%%"

# Every shape observed or plausibly emitted by an LLM. Grows over time;
# additions here are free — they only strengthen the pin.
CORPUS = [
    pytest.param(OBJ, id="bare-object"),
    pytest.param(LONG, id="nested-object"),
    pytest.param("```json\n" + OBJ + "\n```", id="fenced-json"),
    pytest.param("```\n" + OBJ + "\n```", id="fenced-bare"),
    pytest.param("Here is the extracted data:\n" + OBJ, id="prose-prefix"),
    pytest.param("Here is the data:\n```json\n" + OBJ + "\n```", id="prose-and-fence"),
    pytest.param("```json\n" + OBJ + "\n```\nLet me know.", id="trailing-prose"),
    pytest.param("\n" + OBJ, id="leading-newline"),
    pytest.param("<result>\n" + OBJ + "\n</result>", id="xml-wrapped"),
    pytest.param(LONG[:60], id="truncated-mid-value"),
    pytest.param(LONG[:45], id="truncated-mid-key"),
    pytest.param(LONG[:120], id="truncated-in-array"),
    pytest.param(LONG[:-1], id="truncated-last-brace"),
    pytest.param(OBJ + "," + '{"b": 2}', id="two-objects-comma"),
    pytest.param(OBJ + "\n" + '{"b": 2}', id="two-objects-newline"),
    pytest.param('{"a": 1},{"b": 2},{"c": 3', id="fragmented-truncated"),
    pytest.param("[" + OBJ + "]", id="top-level-array"),
    pytest.param("[" + OBJ + "," + '{"b": 2}]', id="array-of-two"),
    pytest.param("<thinking>\nExtracting.\n</thinking>\n" + OBJ, id="thinking-block"),
    pytest.param("Using schema {f: v} I got:\n" + OBJ, id="prose-with-braces"),
    pytest.param("1. invoice\n2. total\n\n" + OBJ, id="numbered-list"),
    pytest.param(OBJ + '\n\nNote: varies.\n{"b": 2}', id="json-prose-json"),
    pytest.param("", id="empty"),
    pytest.param("not json at all", id="plain-text"),
    pytest.param('{"a": "unterminated', id="unterminated-string"),
    pytest.param('{"a": 1,}', id="trailing-comma"),
    pytest.param("{'a': 1}", id="single-quotes"),
    # --- model explanations alongside the answer ---
    pytest.param(
        "I found the following fields on page 3:\n" + OBJ, id="explanation-prefix"
    ),
    pytest.param(
        OBJ + "\n\nThe total was derived from the line items above.",
        id="explanation-suffix",
    ),
    pytest.param(
        "Analysis:\n- invoice located\n- total summed\n\n" + OBJ, id="bulleted-preamble"
    ),
    pytest.param(
        "The document mentions {placeholders} but the real values are:\n" + OBJ,
        id="explanation-with-braces",
    ),
    pytest.param(
        "I could not locate an invoice number in this document.",
        id="explanation-only-no-json",
    ),
    pytest.param(
        "Here is the JSON:\n" + OBJ + "\nHere it is again:\n" + OBJ,
        id="answer-repeated-twice",
    ),
    # --- code blocks ---
    pytest.param("```python\n" + OBJ + "\n```", id="fence-wrong-language"),
    pytest.param("```JSON\n" + OBJ + "\n```", id="fence-uppercase"),
    pytest.param("```json   \n" + OBJ + "\n```", id="fence-trailing-space"),
    pytest.param("~~~json\n" + OBJ + "\n~~~", id="fence-tilde"),
    pytest.param("`" + OBJ + "`", id="inline-code"),
    pytest.param("```json\n" + OBJ, id="fence-never-closed"),
    pytest.param(
        "First:\n```json\n" + OBJ + '\n```\nSecond:\n```json\n{"b": 2}\n```',
        id="two-fences-with-prose",
    ),
    pytest.param(
        "```json\n" + OBJ + "\n```\n```python\nprint(1)\n```", id="json-then-code-fence"
    ),
    # --- truncation at token limit, at each awkward boundary ---
    pytest.param('{"invoice_number": "INV-0', id="cut-inside-string"),
    pytest.param('{"invoice_number', id="cut-inside-key"),
    pytest.param('{"total": 125', id="cut-inside-number"),
    pytest.param('{"note": "line\\', id="cut-inside-escape"),
    pytest.param('{"note": "\\u00', id="cut-inside-unicode-escape"),
    pytest.param("{", id="cut-after-open-brace"),
    pytest.param('{"line_items": [{"desc": "Widget"', id="cut-inside-nested-object"),
    pytest.param('{"line_items": [{"a":1},{"b":2},', id="cut-after-array-comma"),
    pytest.param("```json\n" + LONG[:70], id="cut-inside-fence"),
    pytest.param("Here is the data:\n" + LONG[:70], id="cut-with-explanation-prefix"),
    # --- highlight / confidence annotated responses (cloud features) ---
    pytest.param(ANNOTATED, id="annotated-comments"),
    pytest.param(WORD_CONF, id="annotated-word-confidence"),
    pytest.param(ANNOTATED_AND_WORD_CONF, id="annotated-both"),
    pytest.param(ANNOTATED[:60], id="annotated-truncated"),
    pytest.param("```json\n" + ANNOTATED + "\n```", id="annotated-fenced"),
    pytest.param('{"url": "https://example.com/a", "total": 1}', id="url-not-a-comment"),
]


@pytest.mark.parametrize("raw", CORPUS)
def test_default_path_matches_pre_un4017_behaviour(raw):
    """No contract => byte-identical to the historical implementation."""
    expected = _original_impl(raw)
    actual = repair_json_with_best_structure(raw)
    assert actual == expected
    assert type(actual) is type(expected)


@pytest.mark.parametrize("raw", CORPUS)
def test_default_path_takes_no_contract_branch(raw):
    """Passing contract=None explicitly is the same as omitting it."""
    assert repair_json_with_best_structure(raw) == repair_json_with_best_structure(
        raw, contract=None
    )


# --- Part 2: opt-in contract path -------------------------------------

KEYS = ("invoice_number", "total")
DICT_CONTRACT = JsonContract(expect=dict, required_keys=KEYS)

# Shapes that previously reached the backend as a list and 500'd on
# ``outputs.get(prompt.prompt_key)``.
LIST_SHAPES = [
    pytest.param("<thinking>\nExtracting.\n</thinking>\n" + OBJ, id="thinking-block"),
    pytest.param("Using schema {f: v} I got:\n" + OBJ, id="prose-with-braces"),
    pytest.param("1. invoice\n2. total\n\n" + OBJ, id="numbered-list"),
    pytest.param(OBJ + "," + '{"b": 2}', id="two-objects"),
    pytest.param(
        "```json\n" + OBJ + "\n```\n```json\n" + '{"b": 2}' + "\n```",
        id="two-fenced-blocks",
    ),
    pytest.param(OBJ + '\n\nNote: varies.\n{"b": 2}', id="json-prose-json"),
    pytest.param("[" + OBJ + "]", id="top-level-array"),
]


@pytest.mark.parametrize("raw", LIST_SHAPES)
def test_contract_recovers_dict_from_list_shapes(raw):
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert isinstance(result, dict), f"still a {type(result).__name__}"
    assert result.get("invoice_number") == "INV-001"


def test_contract_prefers_real_answer_over_quoted_schema():
    """A schema example in prose must not win over the actual answer."""
    raw = 'Using the schema {"invoice_number": "<string>"} I extracted:\n' + OBJ
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert result.get("total") == 1250.5


def test_contract_merges_genuinely_fragmented_object():
    """Truncation recovery — the case the '[' wrap was built for."""
    raw = '{"invoice_number": "INV-001"},{"total": 1250.5}'
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert result == {"invoice_number": "INV-001", "total": 1250.5}


def test_contract_does_not_merge_repeated_keys():
    """Repeated keys mean distinct records, not one split object."""
    raw = '{"invoice_number": "A"},{"invoice_number": "B"}'
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    # First wins: candidates are generated in preference order and ties keep
    # the earlier one, so this is deterministic rather than "either is fine".
    assert result == {"invoice_number": "A"}


def test_contract_drops_mangled_fence_debris():
    """Observed in prod: a garbled fence marker survived as a bare string."""
    raw = OBJ + '\n"ապետրյjson"'
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert isinstance(result, dict)
    assert result.get("invoice_number") == "INV-001"


def test_line_item_list_contract_keeps_the_list():
    """A list-shaped answer stays a list — line-item prompts depend on it."""
    raw = '[{"desc": "Widget", "qty": 2}, {"desc": "Gadget", "qty": 7}]'
    result = repair_json_with_best_structure(raw, contract=JsonContract(expect=list))
    assert isinstance(result, list) and len(result) == 2


def test_unsalvageable_returns_legacy_result_for_caller_to_reject():
    """No silent invention — the caller still gets to raise its own 422."""
    raw = "the document could not be read"
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert result == _original_impl(raw)


# --- Part 3: positional metadata must never be reshaped ----------------
#
# highlight_data / confidence_data / line_numbers are mapped onto the parsed
# structure by walking it and popping a flat comment list. Reshaping the value
# shifts that alignment and mislabels which line each field came from — silent
# corruption, strictly worse than the 500 this contract exists to prevent.

ANNOTATED_LIST_SHAPES = [
    pytest.param("<thinking>\nhm\n</thinking>\n" + ANNOTATED, id="thinking-annotated"),
    pytest.param("1. a\n2. b\n\n" + ANNOTATED, id="numbered-annotated"),
    pytest.param(ANNOTATED + "\n" + ANNOTATED, id="two-annotated-objects"),
    pytest.param(WORD_CONF + '\n{"b": 2}', id="word-conf-plus-junk"),
]


@pytest.mark.parametrize("raw", ANNOTATED_LIST_SHAPES)
def test_annotated_responses_are_never_reshaped(raw):
    """Refuse the salvage rather than misalign line numbers."""
    assert repair_json_with_best_structure(raw, contract=DICT_CONTRACT) == _original_impl(
        raw
    )


@pytest.mark.parametrize("raw", ANNOTATED_LIST_SHAPES)
def test_annotated_reshape_is_available_when_caller_opts_in(raw):
    """Escape hatch for callers that do no positional mapping."""
    opted_in = JsonContract(expect=dict, required_keys=KEYS, reshape_annotated=True)
    result = repair_json_with_best_structure(raw, contract=opted_in)
    assert isinstance(result, dict)


def test_url_value_does_not_count_as_an_annotation():
    """`https://` must not be mistaken for a `//` comment."""
    raw = '{"url": "https://example.com"},{"invoice_number": "INV-001"},{"total": 1}'
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert isinstance(result, dict), "URL was misread as positional metadata"


# --- Part 4: raw-payload debug flag ------------------------------------
#
# Raw LLM output is customer document content. The flag alone must not be
# enough to log it — an unset or production REGION has to fail closed.

RAW_FLAG = "DEBUG_LOG_RAW_LLM_RESPONSE"


@pytest.mark.parametrize(
    "flag,environment,expected",
    [
        ("true", "staging", True),
        ("true", "dev", True),
        ("true", "STAGING", True),
        ("true", "production", False),
        ("true", "", False),
        # Unset must fail closed: a worker that never received the var is the
        # likeliest way this would ever leak.
        ("true", None, False),
        # A value nobody anticipated is not an invitation.
        ("true", "prod-eu", False),
        ("true", "us", False),
        ("false", "staging", False),
        (None, "staging", False),
        ("TRUE", "staging", True),
        ("1", "staging", False),
    ],
)
def test_raw_debug_requires_flag_and_non_prod_environment(
    monkeypatch, flag, environment, expected
):
    for name, value in ((RAW_FLAG, flag), ("DEPLOYMENT_ENV", environment)):
        monkeypatch.delenv(name, raising=False)
        if value is not None:
            monkeypatch.setenv(name, value)
    assert _raw_debug_enabled() is expected


def test_region_alone_never_unlocks_raw_logging(monkeypatch):
    """REGION is geography in prod (US/EU) — it must not gate this."""
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("REGION", "STAGING")
    monkeypatch.delenv("DEPLOYMENT_ENV", raising=False)
    assert _raw_debug_enabled() is False


def test_raw_payload_is_not_logged_by_default(monkeypatch, caplog):
    monkeypatch.delenv(RAW_FLAG, raising=False)
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    secret = '{"patient_name": "Jane Roe"},{"ssn": "123-45-6789"}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(secret, contract=DICT_CONTRACT)
    assert "Jane Roe" not in caplog.text
    assert "123-45-6789" not in caplog.text


def test_raw_payload_is_logged_when_enabled_in_staging(monkeypatch, caplog):
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    secret = '{"patient_name": "Jane Roe"},{"ssn": "123-45-6789"}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(secret, contract=DICT_CONTRACT)
    assert "Jane Roe" in caplog.text


def test_log_sink_elides_the_middle_and_keeps_the_end(monkeypatch, caplog):
    """The parse-breaking debris is at the end — it must survive clipping."""
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_MAX_CHARS", "80")
    raw = '{"a": "START' + "x" * 5000 + 'END"},"trailing-debris-json"'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert "chars elided" in caplog.text
    assert "trailing-debris-json" in caplog.text, "tail was clipped"
    assert "START" in caplog.text


def test_webhook_sink_sends_the_untruncated_payload(monkeypatch):
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_SINK", "webhook")
    monkeypatch.setenv("DEBUG_RAW_LLM_WEBHOOK_URL", "http://collector.local/raw")
    raw = '{"a": "' + "x" * 50000 + '"},{"b": 2}'
    sent = {}
    monkeypatch.setattr(
        "executor.executors.json_repair_helper._post_to_webhook",
        lambda url, payload: sent.update(url=url, payload=payload),
    )
    repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert sent["url"] == "http://collector.local/raw"
    assert sent["payload"]["raw_response"] == raw, "payload was truncated"
    assert sent["payload"]["outcome"] == "contract_not_satisfied"


def test_webhook_sink_never_writes_the_payload_to_logs(monkeypatch, caplog):
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_SINK", "webhook")
    monkeypatch.setenv("DEBUG_RAW_LLM_WEBHOOK_URL", "http://collector.local/raw")
    monkeypatch.setattr(
        "executor.executors.json_repair_helper._post_to_webhook",
        lambda url, payload: None,
    )
    secret = '{"patient_name": "Jane Roe"},{"b": 2}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(secret, contract=DICT_CONTRACT)
    assert "Jane Roe" not in caplog.text


def test_webhook_failure_never_breaks_extraction(monkeypatch):
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_SINK", "webhook")
    monkeypatch.setenv("DEBUG_RAW_LLM_WEBHOOK_URL", "http://collector.local/raw")

    def _boom(*args, **kwargs):
        raise ConnectionError("collector down")

    # Patched rather than dialling a real host: a unit test must not depend on
    # DNS, and the point here is the swallow, not the socket.
    monkeypatch.setattr("executor.executors.json_repair_helper._post_to_webhook", _boom)
    raw = OBJ + ',{"b": 2}'
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert result.get("invoice_number") == "INV-001"


def test_shape_trace_is_emitted_without_any_flag(monkeypatch, caplog):
    """The PII-free diagnostic must be available in production as-is."""
    monkeypatch.delenv(RAW_FLAG, raising=False)
    monkeypatch.setenv("DEPLOYMENT_ENV", "production")
    raw = '{"patient_name": "Jane Roe"},{"ssn": "123-45-6789"}'
    with caplog.at_level(logging.WARNING):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert "did NOT satisfy contract" in caplog.text
    assert "annotated=False" in caplog.text
    assert "Jane Roe" not in caplog.text


def test_skeleton_keeps_declared_keys_and_drops_values():
    declared = frozenset({"name", "items", "qty"})
    skeleton = _skeleton({"name": "Jane Roe", "items": [{"qty": 2}]}, declared)
    assert skeleton == {"name": "<str:8>", "items": [{"qty": "<int>"}]}


def test_raw_payload_is_emitted_on_success_too(monkeypatch, caplog):
    """Always-on capture: a clean parse is logged as well as a broken one."""
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(OBJ, contract=DICT_CONTRACT)
    assert "INV-001" in caplog.text
    assert "satisfied" in caplog.text


def test_shape_trace_is_emitted_on_success_at_debug(monkeypatch, caplog):
    monkeypatch.delenv(RAW_FLAG, raising=False)
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(OBJ, contract=DICT_CONTRACT)
    assert "JSON repair satisfied contract" in caplog.text
    assert "INV-001" not in caplog.text, "shape trace must carry no values"


def test_shape_trace_covers_the_no_contract_path(monkeypatch, caplog):
    monkeypatch.delenv(RAW_FLAG, raising=False)
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(OBJ)
    assert "wanted=any" in caplog.text


def test_zero_max_chars_disables_clipping(monkeypatch, caplog):
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_MAX_CHARS", "0")
    raw = '{"a": "' + "x" * 20000 + '"},{"b": 2}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert "elided" not in caplog.text
    assert "x" * 20000 in caplog.text


@pytest.fixture(autouse=True)
def _clear_log_context():
    """`_context` is a thread-local; a set context outlives its test."""
    yield
    from shared.infrastructure.logging import WorkerLogger
    from shared.infrastructure.logging.logger import LogContext

    WorkerLogger.set_context(LogContext())


def test_webhook_payload_carries_correlation_ids(monkeypatch):
    from shared.infrastructure.logging import WorkerLogger
    from shared.infrastructure.logging.logger import LogContext

    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_SINK", "webhook")
    monkeypatch.setenv("DEBUG_RAW_LLM_WEBHOOK_URL", "http://collector.local/raw")
    WorkerLogger.set_context(LogContext(request_id="req-123", execution_id="exec-456"))
    sent = {}
    monkeypatch.setattr(
        "executor.executors.json_repair_helper._post_to_webhook",
        lambda url, payload: sent.update(payload),
    )
    repair_json_with_best_structure(OBJ + ',{"b": 2}', contract=DICT_CONTRACT)
    assert sent["request_id"] == "req-123"
    assert sent["execution_id"] == "exec-456"


def test_log_sink_carries_execution_id(monkeypatch, caplog):
    from shared.infrastructure.logging import WorkerLogger
    from shared.infrastructure.logging.logger import LogContext

    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.delenv("DEBUG_LOG_RAW_LLM_SINK", raising=False)
    WorkerLogger.set_context(LogContext(request_id="req-9", execution_id="exec-9"))
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(OBJ, contract=DICT_CONTRACT)
    assert "execution_id=exec-9" in caplog.text


def test_alignment_mismatch_warns_even_when_parse_succeeds(caplog):
    """A `//` inside a value adds a phantom comment and shifts line numbers.

    The parse succeeds and the output looks fine, so this warning is the only
    signal — the trail a "highlight is on the wrong line" report follows.
    """
    raw = '{\n  "url": "https://x.com/a",\n  "total": 1 // 0x2b\n}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert "MISMATCH" in caplog.text
    assert "WARNING" in caplog.text


def test_alignment_ok_when_every_leaf_has_a_comment(caplog):
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(ANNOTATED, contract=DICT_CONTRACT)
    assert "alignment=comments=2 leaves=2 malformed=0 ok" in caplog.text


def test_alignment_not_computed_for_unannotated_responses(caplog):
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(OBJ, contract=DICT_CONTRACT)
    assert "alignment=n/a" in caplog.text


def test_word_confidence_only_response_is_not_an_alignment_mismatch(caplog):
    """`%%%` without `//` comments is not comment-mapped — nothing to align."""
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(WORD_CONF, contract=DICT_CONTRACT)
    assert "MISMATCH" not in caplog.text
    assert "comments=0 n/a" in caplog.text


def test_webhook_sink_without_url_drops_payload_rather_than_logging_it(
    monkeypatch, caplog
):
    """A typo in the URL must not silently divert document content to logs."""
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_SINK", "webhook")
    monkeypatch.delenv("DEBUG_RAW_LLM_WEBHOOK_URL", raising=False)
    secret = '{"patient_name": "Jane Roe"},{"b": 2}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(secret, contract=DICT_CONTRACT)
    assert "Jane Roe" not in caplog.text
    assert "dropping the raw payload" in caplog.text


def test_skeleton_redacts_keys_the_contract_did_not_declare():
    """Repair promotes document text into key position on malformed input."""
    skeleton = _skeleton({"invoice_number": "x", "Jane Roe": 1}, frozenset(KEYS))
    assert skeleton == {"invoice_number": "<str:1>", "<key:8>": "<int>"}


def test_shape_trace_never_emits_document_text_from_keys(caplog):
    """A dict keyed on document content must not reach the logs."""
    raw = '{"Jane Roe": "patient"},{"b": 2}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert "Jane Roe" not in caplog.text


def test_max_chars_of_one_does_not_emit_the_whole_payload(monkeypatch, caplog):
    """limit//2 == 0 and text[-0:] is the whole string — the cap must hold."""
    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_MAX_CHARS", "1")
    raw = '{"a": "' + "SECRET" * 500 + '"},{"b": 2}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert caplog.text.count("SECRET") <= 1
    assert "chars elided" in caplog.text


# --- Part 5: findings from review ---------------------------------------


def test_bytes_input_still_parses_as_it_always_did():
    """Diagnostics must not narrow the accepted input domain.

    json.loads accepts bytes, so _repair_legacy always did too; a regex scan
    in the diagnostics made it raise TypeError.
    """
    assert repair_json_with_best_structure(b'{"a": 1}') == {"a": 1}
    assert repair_json_with_best_structure(b'{"a": 1}') == _original_impl(b'{"a": 1}')


@pytest.mark.parametrize(
    "value",
    [
        "N/A // pending",
        "docs//archive/2024",
        "row %%% separator",
    ],
    ids=["slashes-in-prose", "path", "stray-marker"],
)
def test_marker_like_text_in_a_value_does_not_disable_the_fix(value):
    """A bare `//` or a lone marker in document text is not an annotation.

    Treating it as one silently switched the reshape guard on and returned a
    list — the exact AttributeError this module exists to prevent.
    """
    raw = f'1. notes\n\n{{"invoice_number": "INV-001", "note": "{value}", "total": 1}}'
    result = repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert isinstance(result, dict), f"{value!r} disabled the salvage"
    assert result.get("invoice_number") == "INV-001"


def test_real_hex_annotation_still_blocks_reshaping():
    """The narrower rule must not lose the protection it exists for."""
    raw = "1. notes\n\n" + ANNOTATED
    assert repair_json_with_best_structure(raw, contract=DICT_CONTRACT) == _original_impl(
        raw
    )


def test_alignment_is_clean_for_annotated_plus_word_confidence(caplog):
    """The consumer strips `%%%` then parses; leaves must come from that too.

    Counting leaves from a parse of the unstripped text made every
    well-formed highlight+word-confidence response report MISMATCH.
    """
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(ANNOTATED_AND_WORD_CONF, contract=DICT_CONTRACT)
    assert "MISMATCH" not in caplog.text
    assert "alignment=comments=2 leaves=2 malformed=0 ok" in caplog.text


def test_word_confidence_marker_env_override_is_honoured(monkeypatch, caplog):
    """The consumer reads WORD_CONFIDENCE_MARKER; hardcoding breaks silently."""
    monkeypatch.setenv("WORD_CONFIDENCE_MARKER", "@@@")
    raw = ANNOTATED + "\n@@@\nINV-001 0.98\n@@@"
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw, contract=DICT_CONTRACT)
    assert "MISMATCH" not in caplog.text


def test_skeleton_redacts_every_key_when_there_is_no_contract(caplog):
    """The no-contract path logs in production, so it must declare nothing."""
    raw = '{"parties": {"Jane Roe": "plaintiff"}},{"b": 2}'
    with caplog.at_level(logging.DEBUG):
        repair_json_with_best_structure(raw)
    assert "Jane Roe" not in caplog.text
    assert "parties" not in caplog.text


def test_diagnostics_failure_cannot_break_a_repair(monkeypatch, caplog):
    """Any future addition inside the trace must not fail an extraction."""

    def _boom(*args, **kwargs):
        raise RuntimeError("diagnostics exploded")

    monkeypatch.setattr("executor.executors.json_repair_helper._shape", _boom)
    # DEBUG so the trace is actually emitted; the args are lazily evaluated
    # behind isEnabledFor, so at WARNING _shape would never be reached.
    with caplog.at_level(logging.DEBUG):
        assert repair_json_with_best_structure(OBJ) == _original_impl(OBJ)
    assert "diagnostics failed" in caplog.text


def test_webhook_is_dispatched_off_the_calling_thread(monkeypatch):
    """A synchronous post would add up to its timeout to every prompt."""
    import threading

    monkeypatch.setenv(RAW_FLAG, "true")
    monkeypatch.setenv("DEPLOYMENT_ENV", "staging")
    monkeypatch.setenv("DEBUG_LOG_RAW_LLM_SINK", "webhook")
    monkeypatch.setenv("DEBUG_RAW_LLM_WEBHOOK_URL", "http://collector.local/raw")
    seen = {}
    done = threading.Event()

    def _fake_post(url, json, timeout):
        seen["thread"] = threading.current_thread().name
        done.set()

    import requests

    monkeypatch.setattr(requests, "post", _fake_post)
    repair_json_with_best_structure(OBJ + ',{"b": 2}', contract=DICT_CONTRACT)
    assert done.wait(5), "webhook never fired"
    assert seen["thread"] != threading.current_thread().name


# --- Part 6: dependency drift -------------------------------------------
#
# Part 1 compares production against _original_impl, but both call the SAME
# installed json_repair, so a version bump moves both sides together and the
# pin stays green. json-repair is declared with a lower bound, and its own
# heuristics are expected to evolve — _reparse_without_wrap exists precisely
# because a newer release can mis-tokenise an intact response. These assert
# absolute values, so a routine `uv lock` refresh that changes what customers
# get fails here instead of shipping.
#
# A failure is NOT necessarily a regression: re-read the new output, decide
# whether it is better or worse, then update the expectation deliberately.


@pytest.mark.parametrize(
    "raw,expected",
    [
        pytest.param(OBJ, {"invoice_number": "INV-001", "total": 1250.5}, id="bare"),
        pytest.param(
            OBJ + ',{"b": 2}',
            [{"invoice_number": "INV-001", "total": 1250.5}, {"b": 2}],
            id="two-objects",
        ),
        pytest.param(
            '{"a": 1},{"b": 2},{"c": 3',
            [{"a": 1}, {"b": 2}, {"c": 3}],
            id="fragmented-truncated",
        ),
        # Documents today's behaviour rather than endorsing it: the wrap
        # candidate shreds an intact fenced response, which is the whole
        # reason the contract path offers an unwrapped candidate.
        pytest.param(
            "```json\n" + OBJ + "\n```",
            ["json\n{", 'invoice_number": "INV-001', {"total": 1250.5}],
            id="fenced-shredded-by-the-wrap",
        ),
    ],
)
def test_no_contract_output_is_pinned_against_library_drift(raw, expected):
    assert repair_json_with_best_structure(raw) == expected


def test_contract_output_is_pinned_against_library_drift():
    """The salvage result customers actually receive, not just its type."""
    raw = "<thinking>\nExtracting.\n</thinking>\n" + OBJ
    assert repair_json_with_best_structure(raw, contract=DICT_CONTRACT) == {
        "invoice_number": "INV-001",
        "total": 1250.5,
    }
