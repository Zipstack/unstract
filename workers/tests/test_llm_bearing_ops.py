"""Every paid operation must be in the no-usage-records backstop.

`execute_extraction` logs when an op in `_LLM_BEARING_OPS` finishes
successfully having emitted no usage records. That log line is the ONLY signal
that a run's billing produced nothing: the cloud `flush()` returns an empty list
rather than raising, so total loss of a job's usage rows is otherwise
indistinguishable from a job that legitimately made no LLM calls.

So leaving a paid op out of the set is not a missing log line, it is a missing
alarm — and the gap is invisible, because the symptom is silence.

`table_extract_api` (the Agent-KV API's table extractor) was absent, which is
how the whole Agent-KV table path shipped with no billing backstop at all.
Reported as 1.2 in the branch review.
"""

from executor.tasks import _LLM_BEARING_OPS

#: Operations known to drive at least one LLM call on every successful run.
#: Add to this list and the set together.
#:
#: **Known limitation of this file.** These are two literals, so the
#: assertions below can only fail when the copies DISAGREE -- never when both
#: are wrong together. A new paid op declared in neither still ships with no
#: billing alarm. The derived version, which asserts every operation in the
#: backend's `EXTRACTOR_ROUTES` is in `_LLM_BEARING_OPS` and so cannot be
#: satisfied by forgetting both, is
#: `backend/agent_kv/tests/test_queue_wiring_is_derived.py`
#: (`test_every_routed_operation_has_a_billing_backstop`). It lives there
#: because `EXTRACTOR_ROUTES` is not importable from this test venv, and
#: `executor.tasks` is not importable from the backend's -- neither side can
#: import both, which is why this pair exists at all.
#:
#: Kept rather than replaced: it covers the four non-Agent-KV paid ops, which
#: `EXTRACTOR_ROUTES` says nothing about.
PAID_OPERATIONS = {
    "answer_prompt",
    "single_pass_extraction",
    "summarize",
    "structure_pipeline",
    # Drives two LLMs (advanced + lite) on every run.
    "table_extract_api",
}


def test_the_table_api_operation_is_covered():
    """The regression this file was added for."""
    assert "table_extract_api" in _LLM_BEARING_OPS


def test_every_known_paid_operation_is_covered():
    missing = PAID_OPERATIONS - _LLM_BEARING_OPS
    assert not missing, (
        f"{sorted(missing)} drive LLM calls but are absent from "
        f"_LLM_BEARING_OPS, so a run of one that emits zero usage records "
        f"logs nothing and the lost billing is silent"
    )


def test_the_set_has_not_quietly_grown_past_what_is_declared_here():
    """The reverse direction, so the two lists stay a real pair rather than one
    drifting into a superset of the other.
    """
    unexpected = _LLM_BEARING_OPS - PAID_OPERATIONS
    assert not unexpected, (
        f"{sorted(unexpected)} were added to _LLM_BEARING_OPS without being "
        f"declared here; add them to PAID_OPERATIONS with a note on what they "
        f"spend"
    )
