"""The constraint evaluator's operator/aggregate matrix, and its drop behaviour.

This file was 0 bytes against a 258-line module -- an empty file with that name
reads as coverage, which is worse than no file (reported as 2.20 in the branch
review). What it covers now is the part the review found wrong (2.19): the
module called itself fail-closed while a constraint that raises is reported as
"no violation", and a partial sum over a column with one blank cell produced a
false violation on a correct document.

`test_constraints_tolerance.py` covers the float-tolerance derivation; this
covers everything else.
"""

import ast
import logging

import pytest

from unstract.agent_kv_schema import evaluate_constraints
from unstract.agent_kv_schema.compile import _ALLOWED_CALLS, _ALLOWED_NODES
from unstract.agent_kv_schema.constraints import _AGG, _BIN, _CMP

_ROWS = {
    "lines": [
        {"amount": "100.00", "qty": "2", "sku": "A"},
        {"amount": "50.00", "qty": "1", "sku": "B"},
    ]
}


# --------------------------------------------------------------------------
# The comparison and arithmetic matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "values", "violated"),
    [
        ("a == b", {"a": "1", "b": "1"}, False),
        ("a == b", {"a": "1", "b": "2"}, True),
        ("a != b", {"a": "1", "b": "2"}, False),
        ("a != b", {"a": "1", "b": "1"}, True),
        ("a < b", {"a": "1", "b": "2"}, False),
        ("a < b", {"a": "2", "b": "2"}, True),
        ("a <= b", {"a": "2", "b": "2"}, False),
        ("a > b", {"a": "3", "b": "2"}, False),
        ("a >= b", {"a": "2", "b": "2"}, False),
        # chained, Python-style
        ("a < b < c", {"a": "1", "b": "2", "c": "3"}, False),
        ("a < b < c", {"a": "1", "b": "3", "c": "2"}, True),
        # arithmetic
        ("total == net + tax", {"total": "110", "net": "100", "tax": "10"}, False),
        ("total == net + tax", {"total": "111", "net": "100", "tax": "10"}, True),
        ("net == total - tax", {"net": "100", "total": "110", "tax": "10"}, False),
        ("total == qty * price", {"total": "20", "qty": "4", "price": "5"}, False),
        ("price == total / qty", {"price": "5", "total": "20", "qty": "4"}, False),
        ("a == -b", {"a": "-5", "b": "5"}, False),
        # boolean composition
        ("a > 0 and b > 0", {"a": "1", "b": "1"}, False),
        ("a > 0 and b > 0", {"a": "1", "b": "-1"}, True),
        ("a > 0 or b > 0", {"a": "-1", "b": "1"}, False),
        ("not (a > b)", {"a": "1", "b": "2"}, False),
        # thousands separators and currency symbols coerce numerically
        ("a == b", {"a": "9,000", "b": "9000"}, False),
        ("a == b", {"a": "$1,234.50", "b": "1234.5"}, False),
        # ISO dates compare lexicographically as strings
        ("start < end", {"start": "2026-01-01", "end": "2026-02-01"}, False),
        ("start < end", {"start": "2026-03-01", "end": "2026-02-01"}, True),
    ],
)
def test_operator_matrix(expr, values, violated):
    assert evaluate_constraints([expr], values, {}) == ([expr] if violated else [])


@pytest.mark.parametrize(
    "expr",
    [
        "a == b",  # 'a' missing entirely
        "missing == 1",  # operand absent
        "a == 1",  # operand empty string
        "a < b",  # number vs string: not like-typed
        "a == 'nan'",  # non-finite token stays a string
    ],
)
def test_unusable_operands_are_skipped_not_violations(expr):
    values = {"a": "", "b": "text"}
    assert evaluate_constraints([expr], values, {}) == []


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "values", "violated"),
    [
        ("total == sum('lines.amount')", {"total": "150.00"}, False),
        ("total == sum('lines.amount')", {"total": "150.01"}, True),
        ("n == count('lines')", {"n": "2"}, False),
        ("n == count('lines')", {"n": "3"}, True),
        ("n == count('lines.sku')", {"n": "2"}, False),
        ("lo == min('lines.amount')", {"lo": "50"}, False),
        ("hi == max('lines.amount')", {"hi": "100"}, False),
        ("mean == avg('lines.amount')", {"mean": "75"}, False),
        ("mean == avg('lines.amount')", {"mean": "76"}, True),
    ],
)
def test_aggregate_matrix(expr, values, violated):
    assert evaluate_constraints([expr], values, _ROWS) == ([expr] if violated else [])


@pytest.mark.parametrize(
    "expr",
    [
        "x == sum('nosucharray.amount')",  # array not supplied
        "x == sum('lines')",  # sum needs a column
        "x == avg('lines')",
        "x == min('lines')",
        "x == sum('lines.sku')",  # no numeric cell at all
        "x == median('lines.amount')",  # not in the allowlist
        "x == sum('lines.amount', 2)",  # two args
        "x == sum(column)",  # arg is not a string literal
    ],
)
def test_unusable_aggregates_are_skipped_not_violations(expr):
    assert evaluate_constraints([expr], {"x": "150"}, _ROWS) == []


def test_count_of_a_column_counts_non_empty_cells_only():
    rows = {"lines": [{"sku": "A"}, {"sku": ""}, {"sku": "   "}, {"sku": "C"}]}
    assert evaluate_constraints(["n == count('lines.sku')"], {"n": "2"}, rows) == []
    assert evaluate_constraints(["n == count('lines')"], {"n": "4"}, rows) == []


# --------------------------------------------------------------------------
# 2.19: a PARTIAL sum/avg must skip, not report a false violation
# --------------------------------------------------------------------------

_PARTIAL = {
    "lines": [
        {"amount": "100.00"},
        {"amount": ""},  # blank cell: OCR missed it, or the row has no amount
        {"amount": "50.00"},
    ]
}


def test_a_partial_sum_skips_rather_than_reporting_a_false_violation():
    """The document is CORRECT: 100 + <missing> + 50 against a stated 200.

    Summing the two readable cells gives 150, which is not 200 -- so before
    the fix this reported a violation on a correct invoice. One blank cell in
    a long array was enough. The sum is not the column's sum, so there is
    nothing to compare and the constraint is advisory-skipped.
    """
    expr = "total == sum('lines.amount')"
    assert evaluate_constraints([expr], {"total": "200.00"}, _PARTIAL) == []


def test_a_partial_avg_also_skips():
    expr = "mean == avg('lines.amount')"
    assert evaluate_constraints([expr], {"mean": "66.67"}, _PARTIAL) == []


def test_an_un_parseable_cell_counts_as_missing_for_sum():
    """`total` is the document's real total, including the cell OCR mangled.

    Summing only the readable cell gives 100 against a stated 250, so without
    the guard this is a violation on a correct document.
    """
    rows = {"lines": [{"amount": "100.00"}, {"amount": "n/a"}]}
    expr = "total == sum('lines.amount')"
    assert evaluate_constraints([expr], {"total": "250.00"}, rows) == []


@pytest.mark.parametrize("fn", ["min", "max", "count"])
def test_min_max_and_count_stay_total_over_a_subset(fn):
    """These are meaningful over the rows that HAVE a value, so they must not skip."""
    expected = {"min": "50.00", "max": "100.00", "count": "2"}[fn]
    expr = f"x == {fn}('lines.amount')"
    assert evaluate_constraints([expr], {"x": expected}, _PARTIAL) == []


# --------------------------------------------------------------------------
# 2.19: a constraint that RAISES is dropped and reported as no violation.
# That stays true (one bad constraint must not fail an extraction) but it is
# now logged, which is the part that was missing.
# --------------------------------------------------------------------------


def test_a_dropped_constraint_is_logged_at_exception_level(caplog):
    """`quantity` normalizes to 0 -> ZeroDivisionError -> dropped.

    `_BIN` includes truediv and `compile._ALLOWED_NODES` includes ast.Div, so
    this expression is accepted at submit: the path is reachable, not
    theoretical.
    """
    expr = "unit_price == line_total / quantity"
    values = {"unit_price": "5", "line_total": "20", "quantity": "0"}
    with caplog.at_level(logging.ERROR, logger="unstract.agent_kv_schema.constraints"):
        assert evaluate_constraints([expr], values, {}) == []
    assert any(
        "DROPPED" in r.getMessage() and expr in r.getMessage() for r in caplog.records
    ), (
        "a constraint that raised was dropped silently; the only signal that "
        "nothing was checked is this log line"
    )


def test_an_ordinary_skip_is_not_logged_as_an_error(caplog):
    """A missing operand is normal on a document with optional keys."""
    with caplog.at_level(logging.WARNING, logger="unstract.agent_kv_schema.constraints"):
        assert evaluate_constraints(["a == b"], {"a": "1"}, {}) == []
    assert caplog.records == []


def test_one_dropped_constraint_does_not_stop_the_others():
    exprs = ["unit_price == line_total / quantity", "total == net"]
    values = {
        "unit_price": "5",
        "line_total": "20",
        "quantity": "0",
        "total": "1",
        "net": "2",
    }
    assert evaluate_constraints(exprs, values, {}) == ["total == net"]


# --------------------------------------------------------------------------
# 2.20: the two hand-maintained allowlists live in two files with nothing
# enforcing agreement. compile.py decides what a submit ACCEPTS; constraints.py
# decides what the evaluator can RUN. A node accepted but not runnable is a
# constraint that is silently skipped for every document; a node runnable but
# not accepted is dead code.
# --------------------------------------------------------------------------


def test_the_submit_allowlist_and_the_evaluator_agree_on_comparisons():
    accepted = {n for n in _ALLOWED_NODES if issubclass(n, ast.cmpop)}
    assert accepted == set(_CMP), (
        "compile._ALLOWED_NODES and constraints._CMP disagree: a comparison "
        "accepted at submit but absent from _CMP is skipped for every document"
    )


def test_the_submit_allowlist_and_the_evaluator_agree_on_arithmetic():
    accepted = {n for n in _ALLOWED_NODES if issubclass(n, ast.operator)}
    assert accepted == set(
        _BIN
    ), "compile._ALLOWED_NODES and constraints._BIN disagree on binary operators"


def test_the_submit_allowlist_and_the_evaluator_agree_on_aggregates():
    assert _ALLOWED_CALLS == _AGG, (
        "compile._ALLOWED_CALLS and constraints._AGG disagree: a function name "
        "accepted at submit but absent from _AGG is skipped for every document"
    )
