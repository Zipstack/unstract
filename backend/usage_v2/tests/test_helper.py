"""Regression tests for ``UsageHelper.get_usage_by_model``.

These tests cover the defensive filter that drops unlabeled LLM rows
from the per-model usage breakdown.  The filter prevents a malformed
bare ``"llm"`` bucket from leaking into API deployment responses when
a producer-side LLM call site forgets to set ``llm_usage_reason``.

The tests exercise only the helper's in-memory aggregation logic, not
the ORM.  We rebind the ``Usage`` symbol the helper resolved at import
to a fake whose ``objects.filter`` chain returns a deterministic list
of row dicts shaped exactly like the real
``.values(...).annotate(...)`` queryset rows the helper iterates over.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import usage_v2.helper as helper_mod
from usage_v2.helper import UsageHelper


class FakeUsage:
    # objects is a MagicMock so each test can rebind filter.return_value.
    objects = MagicMock(name="Usage.objects")


# Swap the symbol get_usage_by_model resolves; leaves the real model untouched.
helper_mod.Usage = FakeUsage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubQueryset:
    """Mimic the chain ``.filter(...).values(...).annotate(...)``."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def values(self, *args: Any, **kwargs: Any) -> _StubQueryset:
        return self

    def annotate(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self._rows


def _row(
    *,
    usage_type: str,
    llm_reason: str,
    model_name: str = "gpt-4o",
    sum_input: int = 0,
    sum_output: int = 0,
    sum_total: int = 0,
    sum_embedding: int = 0,
    sum_cost: float = 0.0,
) -> dict[str, Any]:
    """Build a row matching the shape returned by the helper's
    ``.values(...).annotate(...)`` queryset.
    """
    return {
        "usage_type": usage_type,
        "llm_usage_reason": llm_reason,
        "model_name": model_name,
        "sum_input_tokens": sum_input,
        "sum_output_tokens": sum_output,
        "sum_total_tokens": sum_total,
        "sum_embedding_tokens": sum_embedding,
        "sum_cost": sum_cost,
    }


def _stub_rows(rows: list[dict[str, Any]]) -> None:
    """Make ``Usage.objects.filter(...).values(...).annotate(...)`` yield
    the given rows when the helper is invoked next.
    """
    FakeUsage.objects.filter.return_value = _StubQueryset(rows)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_unlabeled_llm_row_is_dropped() -> None:
    """An ``llm`` row with empty ``llm_usage_reason`` must not produce a
    bare ``"llm"`` bucket in the response — it should be silently
    dropped, while the legitimate extraction row is preserved.
    """
    _stub_rows(
        [
            _row(
                usage_type="llm",
                llm_reason="extraction",
                sum_input=100,
                sum_output=50,
                sum_total=150,
                sum_cost=0.05,
            ),
            _row(
                usage_type="llm",
                llm_reason="",  # the bug — no reason set
                sum_cost=0.01,
            ),
        ]
    )

    result = UsageHelper.get_usage_by_model("00000000-0000-0000-0000-000000000001")

    assert "llm" not in result, (
        "Unlabeled llm row should be dropped — bare 'llm' bucket leaked"
    )
    assert "extraction_llm" in result
    assert len(result["extraction_llm"]) == 1
    entry = result["extraction_llm"][0]
    assert entry["model_name"] == "gpt-4o"
    assert entry["input_tokens"] == 100
    assert entry["output_tokens"] == 50
    assert entry["total_tokens"] == 150
    assert entry["cost_in_dollars"] == "0.05"


def test_embedding_row_is_preserved() -> None:
    """An ``embedding`` row legitimately has empty ``llm_usage_reason``;
    the defensive filter must NOT drop it.  Proves the guard is scoped
    to ``usage_type == 'llm'``.
    """
    _stub_rows(
        [
            _row(
                usage_type="embedding",
                llm_reason="",
                model_name="text-embedding-3-small",
                sum_embedding=200,
                sum_cost=0.001,
            ),
        ]
    )

    result = UsageHelper.get_usage_by_model("00000000-0000-0000-0000-000000000002")

    assert "embedding" in result, "Embedding row was incorrectly dropped"
    assert len(result["embedding"]) == 1
    entry = result["embedding"][0]
    assert entry["model_name"] == "text-embedding-3-small"
    assert entry["embedding_tokens"] == 200
    assert entry["cost_in_dollars"] == "0.001"


def test_all_three_llm_reasons_coexist() -> None:
    """All three labelled LLM buckets (extraction, challenge, summarize)
    must appear with correct token counts when present.
    """
    _stub_rows(
        [
            _row(
                usage_type="llm",
                llm_reason="extraction",
                model_name="gpt-4o",
                sum_input=100,
                sum_output=50,
                sum_total=150,
                sum_cost=0.05,
            ),
            _row(
                usage_type="llm",
                llm_reason="challenge",
                model_name="gpt-4o-mini",
                sum_input=20,
                sum_output=10,
                sum_total=30,
                sum_cost=0.002,
            ),
            _row(
                usage_type="llm",
                llm_reason="summarize",
                model_name="gpt-4o",
                sum_input=300,
                sum_output=80,
                sum_total=380,
                sum_cost=0.07,
            ),
        ]
    )

    result = UsageHelper.get_usage_by_model("00000000-0000-0000-0000-000000000003")

    assert set(result.keys()) == {"extraction_llm", "challenge_llm", "summarize_llm"}
    assert "llm" not in result

    extraction = result["extraction_llm"][0]
    assert extraction["model_name"] == "gpt-4o"
    assert extraction["input_tokens"] == 100
    assert extraction["output_tokens"] == 50
    assert extraction["total_tokens"] == 150

    challenge = result["challenge_llm"][0]
    assert challenge["model_name"] == "gpt-4o-mini"
    assert challenge["input_tokens"] == 20
    assert challenge["output_tokens"] == 10
    assert challenge["total_tokens"] == 30

    summarize = result["summarize_llm"][0]
    assert summarize["model_name"] == "gpt-4o"
    assert summarize["input_tokens"] == 300
    assert summarize["output_tokens"] == 80
    assert summarize["total_tokens"] == 380
