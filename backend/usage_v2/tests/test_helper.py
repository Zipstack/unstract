"""Regression tests for ``UsageHelper.get_usage_by_model``.

These tests cover the defensive filter that drops unlabeled LLM rows
from the per-model usage breakdown.  The filter prevents a malformed
bare ``"llm"`` bucket from leaking into API deployment responses when
a producer-side LLM call site forgets to set ``llm_usage_reason``.

The tests deliberately do not require a live Django database — the
backend test environment has no ``pytest-django``, no SQLite fallback,
and uses ``django-tenants`` against Postgres in production.  Instead
the tests stub ``account_usage.models`` and ``usage_v2.models`` in
``sys.modules`` *before* importing the helper, so the helper module
loads cleanly without triggering Django's app registry checks.  The
fake ``Usage.objects.filter`` chain returns a deterministic list of
row dicts shaped exactly like the real ``.values(...).annotate(...)``
queryset rows the helper iterates over.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Module-level stubs.  Must run BEFORE ``usage_v2.helper`` is imported, so we
# do it at import time and capture the helper reference for the tests below.
# ---------------------------------------------------------------------------


def _install_stubs() -> tuple[Any, Any]:
    """Install fake ``account_usage.models`` and ``usage_v2.models`` modules
    so that ``usage_v2.helper`` can be imported without Django being set up.

    Returns ``(UsageHelper, FakeUsage)`` — the helper class to test and the
    fake Usage class whose ``objects.filter`` we will swap per-test.
    """
    # Fake account_usage package + models module
    if "account_usage" not in sys.modules:
        account_usage_pkg = types.ModuleType("account_usage")
        account_usage_pkg.__path__ = []  # mark as package
        sys.modules["account_usage"] = account_usage_pkg
    if "account_usage.models" not in sys.modules:
        account_usage_models = types.ModuleType("account_usage.models")
        account_usage_models.PageUsage = MagicMock(name="PageUsage")
        sys.modules["account_usage.models"] = account_usage_models

    # Fake usage_v2.models with a Usage class whose ``objects`` is a
    # MagicMock (so each test can rebind ``filter.return_value``).
    if "usage_v2.models" not in sys.modules or not hasattr(
        sys.modules["usage_v2.models"], "_is_test_stub"
    ):
        usage_v2_models = types.ModuleType("usage_v2.models")
        usage_v2_models._is_test_stub = True

        class _FakeUsage:
            objects = MagicMock(name="Usage.objects")

        usage_v2_models.Usage = _FakeUsage
        sys.modules["usage_v2.models"] = usage_v2_models

    # Now import the helper — this picks up our stubs.
    from usage_v2.helper import UsageHelper

    return UsageHelper, sys.modules["usage_v2.models"].Usage


UsageHelper, FakeUsage = _install_stubs()


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
