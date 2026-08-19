"""JSON repair utility functions.

Copied from prompt-service/.../utils/json_repair_helper.py — already Flask-free.

Two entry points, deliberately separated:

``repair_json_with_best_structure(json_str)``
    Untouched legacy behaviour. Every historical caller keeps the exact
    result it got before — see ``_repair_legacy``, which must not be
    edited (UN-4017).

``repair_json_with_best_structure(json_str, contract=...)``
    Opt-in. Runs the same legacy parse, then — only if the result does
    not satisfy the caller's contract — tries the salvage strategies in
    ``_SALVAGERS``. A caller that passes no contract can never reach
    this code, so enhancements here cannot regress existing paths.

To handle a newly observed LLM response shape, add one ``@salvager``
function plus a test case. Do not modify ``_repair_legacy``.
"""

import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Raw LLM output is customer document content. It goes to a dedicated logger so
# it can be routed or dropped at the sink independently of everything else, and
# it must never reach ``publish_log`` — that feeds the user-visible execution
# log stream and the ENABLE_LOG_HISTORY table.
raw_logger = logging.getLogger("unstract.debug.raw_llm")

_RAW_DEBUG_DEFAULT_MAX_CHARS = 4000


# Environments where logging document content is acceptable. An allowlist, not
# a "not production" check: an unset or unrecognised REGION must fail closed,
# otherwise a worker that simply never received the var would start logging
# customer data. REGION is US/EU in production.
_NON_PROD_REGIONS = frozenset({"STAGING", "DEV", "INTEGRATION", "LOCAL"})


def _raw_debug_enabled() -> bool:
    """Whether raw LLM payloads may be logged.

    Read per call so a test can toggle it; flipping it for real needs a pod
    restart either way. Requires both the flag and a non-prod REGION, so
    setting the flag in production cannot dump document content — a flag that
    *can* be enabled in prod eventually will be.
    """
    enabled = os.getenv("DEBUG_LOG_RAW_LLM_RESPONSE", "false").lower() == "true"
    return enabled and os.getenv("REGION", "").strip().upper() in _NON_PROD_REGIONS


def _head_tail(text: str) -> str:
    """Clip the middle, never the end.

    Only used for the ``log`` sink, where the backend clips a single entry at
    ~256KB anyway. The debris that breaks parsing — a trailing fence marker,
    closing prose, an unterminated string — is at the END of the response, so
    head-only truncation removes exactly the evidence worth having. Use the
    ``webhook`` sink when the full payload is needed.
    """
    try:
        limit = int(
            os.getenv("DEBUG_LOG_RAW_LLM_MAX_CHARS", _RAW_DEBUG_DEFAULT_MAX_CHARS)
        )
    except ValueError:
        limit = _RAW_DEBUG_DEFAULT_MAX_CHARS
    if len(text) <= limit:
        return text
    half = limit // 2
    dropped = len(text) - (half * 2)
    return f"{text[:half]}…[{dropped} chars elided]…{text[-half:]}"


def _post_to_webhook(url: str, payload: dict[str, Any]) -> None:
    """Ship the full payload out of band, so it never enters the log pipeline.

    Fire and forget: a debug sink must never slow down or fail an extraction,
    so this swallows every error and never retries.
    """
    try:
        import requests

        requests.post(url, json=payload, timeout=(2, 5))
    except Exception as exc:  # noqa: BLE001 - diagnostics must not raise
        logger.warning("raw LLM debug webhook failed: %s", type(exc).__name__)


def _emit_raw_payload(json_str: str, context: dict[str, Any]) -> None:
    """Send the raw response to the configured sink.

    ``webhook`` sends it whole and keeps it out of logs entirely; ``log``
    (the default) writes a middle-elided copy to the dedicated logger.
    """
    sink = os.getenv("DEBUG_LOG_RAW_LLM_SINK", "log").strip().lower()
    url = os.getenv("DEBUG_RAW_LLM_WEBHOOK_URL", "").strip()
    if sink == "webhook" and url:
        _post_to_webhook(url, {**context, "raw_response": json_str})
        return
    if sink == "webhook":
        logger.warning(
            "DEBUG_LOG_RAW_LLM_SINK=webhook but DEBUG_RAW_LLM_WEBHOOK_URL is unset"
        )
    raw_logger.warning(
        "raw LLM response (%s): %s", context.get("reason", ""), _head_tail(json_str)
    )


def _shape(value: Any, sample: int = 8) -> str:
    """Structural description carrying no document content.

    Safe to emit in production — this is what makes the raw-payload flag
    rarely necessary in the first place.
    """
    if isinstance(value, dict):
        return f"dict(keys={len(value)})"
    if isinstance(value, list):
        kinds = [type(el).__name__ for el in value[:sample]]
        suffix = ", …" if len(value) > sample else ""
        return f"list(len={len(value)}, elements=[{', '.join(kinds)}{suffix}])"
    if isinstance(value, str):
        return f"str(len={len(value)})"
    return type(value).__name__


def _skeleton(value: Any, depth: int = 3) -> Any:
    """Structure with every leaf replaced by its type — keys, never values.

    Keys are prompt field names (schema, author-defined), not extracted
    document content, so this stays safe to log by default.
    """
    if depth < 0:
        return "…"
    if isinstance(value, dict):
        return {k: _skeleton(v, depth - 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_skeleton(el, depth - 1) for el in value[:8]]
    if isinstance(value, str):
        return f"<str:{len(value)}>"
    return f"<{type(value).__name__}>"


# Highlight / confidence / line-number extraction annotates the response with
# ``// 0x..`` comments per value and ``%%%``-delimited word-confidence blocks,
# then maps them onto the parsed structure POSITIONALLY — a flat comment list
# popped during a recursive walk (see the cloud highlight_data plugin's
# ``_process_json`` / ``map_comments``). Any reshape of the parsed value shifts
# that alignment and silently attaches line numbers to the wrong fields, which
# is worse than the error we are fixing. Detect the annotations and refuse to
# reshape. ``(?<![:\w])`` keeps URLs such as ``https://`` from matching.
_ANNOTATED_RESPONSE = re.compile(r"%%%|(?<![:\w])//")


def _is_annotated(json_str: str) -> bool:
    """True when a positional metadata pass depends on the exact structure.

    Known gap (accepted, UN-4017): the consumer side extracts comments with
    ``re.findall(r"//(.*)")`` over the raw text, so a *value* containing ``//``
    — a URL, a path, ``"N/A // pending"`` — reads as a comment. On a line with
    no real hex comment that adds an entry and shifts every later field's line
    number: the same offset class as the PR #546 regression. Not fixed here;
    revisit if it is ever observed or reported.
    """
    return bool(_ANNOTATED_RESPONSE.search(json_str))


def _repair_legacy(json_str: str) -> Any:
    """Original repair logic, preserved verbatim.

    The ``"[" + json_str`` candidate exists to recover *truncated or
    fragmented* responses — objects emitted without their opening
    bracket, e.g. ``{...},{...},{...``. ``len(parsed_with_wrap) > 1`` is
    the fragmentation signal. Two years of edge cases are encoded here;
    changing any branch changes behaviour for inputs nobody has a test
    for. Layer fixes in ``_SALVAGERS`` instead.
    """
    # Fast path — try strict JSON first
    try:
        return json.loads(json_str)
    except ValueError:
        pass

    # Try to import json_repair for advanced repair
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
        # json_repair not installed — return the raw string
        return json_str


@dataclass(frozen=True)
class JsonContract:
    """What the caller needs the parsed value to look like.

    ``required_keys`` disambiguates when several candidate values survive
    parsing — without it, "pick the first dict" can return a schema
    example quoted in the model's prose, or a fragment holding one field,
    instead of the real answer.
    """

    expect: type = dict
    required_keys: tuple[str, ...] = field(default_factory=tuple)
    # Only set when the caller does no positional comment mapping. Reshaping
    # an annotated response misaligns line numbers and word confidences.
    reshape_annotated: bool = False

    def satisfied_by(self, value: Any) -> bool:
        if not isinstance(value, self.expect):
            return False
        if self.expect is dict and self.required_keys:
            return any(k in value for k in self.required_keys)
        return bool(value) or not self.required_keys

    def score(self, value: Any) -> int:
        """How complete a candidate is. Candidates compete on this."""
        if self.expect is dict and isinstance(value, dict):
            return sum(k in value for k in self.required_keys)
        return 0


# A salvager returns a repaired value, or None when it does not apply.
Salvager = Callable[[Any, str, JsonContract], Any]
_SALVAGERS: list[tuple[str, Salvager]] = []


def salvager(name: str) -> Callable[[Salvager], Salvager]:
    """Register a salvage strategy. Order of registration is try-order."""

    def register(fn: Salvager) -> Salvager:
        _SALVAGERS.append((name, fn))
        return fn

    return register


def _is_junk(element: Any) -> bool:
    """Non-container leftovers from prose, fences or reasoning preambles.

    Only leading/trailing scalars are ever dropped by callers of this —
    a scalar is never a valid member of a dict-shaped answer.
    """
    return not isinstance(element, (dict, list))


@salvager("unwrap_single")
def _unwrap_single(value: Any, raw: str, contract: JsonContract) -> Any:
    """``[{...}]`` where the caller wants the object itself."""
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return None


@salvager("drop_junk_elements")
def _drop_junk_elements(value: Any, raw: str, contract: JsonContract) -> Any:
    """Discard scalar debris that faked a fragmentation signal.

    Covers ``<thinking>`` preambles, numbered lists, trailing mangled
    fence markers (``"...json"``) — anything that added a bare string or
    number alongside the real object.
    """
    if not isinstance(value, list):
        return None
    kept = [el for el in value if not _is_junk(el)]
    if len(kept) == len(value):
        return None
    if len(kept) == 1 and isinstance(kept[0], dict):
        return kept[0]
    return kept or None


@salvager("pick_complete_match")
def _pick_complete_match(value: Any, raw: str, contract: JsonContract) -> Any:
    """An element already holds every required key — prefer it untouched.

    Guards against picking a schema example the model quoted in prose,
    which scores zero required keys, and against merging sibling records
    that each happen to carry one field.
    """
    if not isinstance(value, list) or not contract.required_keys:
        return None
    for element in value:
        if isinstance(element, dict) and all(
            k in element for k in contract.required_keys
        ):
            return element
    return None


@salvager("merge_fragments")
def _merge_fragments(value: Any, raw: str, contract: JsonContract) -> Any:
    """Genuine truncation recovery: one object split across fragments.

    This is the case the ``"["`` wrap was built for. Merged only when
    the fragments do not disagree — a repeated key means these are
    distinct records (a line-item list), not one split object.
    """
    if not isinstance(value, list) or contract.expect is not dict:
        return None
    dicts = [el for el in value if isinstance(el, dict)]
    if len(dicts) < 2 or len(dicts) != len(value):
        return None
    merged: dict[str, Any] = {}
    for fragment in dicts:
        if any(k in merged for k in fragment):
            return None
        merged.update(fragment)
    return merged or None


@salvager("pick_best_partial")
def _pick_best_partial(value: Any, raw: str, contract: JsonContract) -> Any:
    """Last resort — the dict carrying the most required keys."""
    if not isinstance(value, list) or not contract.required_keys:
        return None
    dicts = [el for el in value if isinstance(el, dict)]
    if not dicts:
        return None
    best = max(dicts, key=contract.score)
    return best if contract.score(best) else None


def _log_cleansing_chain(json_str: str, parsed: Any, contract: JsonContract) -> None:
    """Emit the step-by-step parse trace for a response that failed its contract.

    Structure only, at WARNING, so every production failure is diagnosable
    without enabling anything. Which step mangled the response is the question
    this answers — reconstructing it after the fact needs the whole chain.
    """
    as_is = _reparse_without_wrap(json_str)
    logger.warning(
        "JSON repair did not satisfy contract | raw=%s annotated=%s | "
        "legacy=%s | unwrapped=%s | wanted=%s keys=%s | skeleton=%s",
        _shape(json_str),
        _is_annotated(json_str),
        _shape(parsed),
        _shape(as_is),
        contract.expect.__name__,
        list(contract.required_keys),
        json.dumps(_skeleton(parsed), ensure_ascii=False)[:500],
    )
    if _raw_debug_enabled():
        _emit_raw_payload(
            json_str,
            {
                "reason": "contract_not_satisfied",
                "expected": contract.expect.__name__,
                "required_keys": list(contract.required_keys),
                "legacy_shape": _shape(parsed),
                "annotated": _is_annotated(json_str),
                "region": os.getenv("REGION", ""),
            },
        )


def _reparse_without_wrap(json_str: str) -> Any:
    """Parse without the ``"["`` prefix.

    The wrap recovers fragmented output, but on newer json_repair
    releases it can also mis-tokenise an intact response and shred it
    into fragments — in which case the unwrapped parse is the intact
    one. Offered as a competing candidate, never as a replacement.
    """
    try:
        from json_repair import repair_json

        return repair_json(json_str=json_str, return_objects=True, ensure_ascii=False)
    except Exception:
        return None


def _candidates(parsed: Any, json_str: str, contract: JsonContract):
    """Every value worth considering, in preference order for ties."""
    for source in (parsed, _reparse_without_wrap(json_str)):
        if source is None:
            continue
        yield source
        for name, strategy in _SALVAGERS:
            try:
                salvaged = strategy(source, json_str, contract)
            except Exception:
                logger.warning("json salvage strategy %s raised; skipping", name)
                continue
            if salvaged is not None:
                yield salvaged


def repair_json_with_best_structure(
    json_str: str, contract: JsonContract | None = None
) -> Any:
    """Intelligently repair JSON string using the best parsing strategy.

    Args:
        json_str: The JSON string to repair
        contract: Optional shape the caller requires. When omitted the
            result is exactly what this function has always returned.

    Returns:
        The parsed JSON object with the best structure. With a contract,
        the most complete candidate satisfying it, otherwise the legacy
        result unchanged so the caller can reject it explicitly.
    """
    parsed = _repair_legacy(json_str)
    if contract is None or contract.satisfied_by(parsed):
        return parsed

    _log_cleansing_chain(json_str, parsed, contract)

    if not contract.reshape_annotated and _is_annotated(json_str):
        logger.warning(
            "Response carries positional metadata; refusing to reshape so "
            "line numbers and word confidences stay aligned"
        )
        return parsed

    best: Any = None
    best_score = -1
    for candidate in _candidates(parsed, json_str, contract):
        if not contract.satisfied_by(candidate):
            continue
        score = contract.score(candidate)
        if score > best_score:
            best, best_score = candidate, score

    if best is None:
        logger.warning(
            "LLM JSON did not satisfy contract (got %s, wanted %s); no salvage applied",
            type(parsed).__name__,
            contract.expect.__name__,
        )
        return parsed

    logger.info(
        "Recovered %s from malformed LLM JSON (matched %d/%d expected keys)",
        contract.expect.__name__,
        best_score,
        len(contract.required_keys),
    )
    return best
