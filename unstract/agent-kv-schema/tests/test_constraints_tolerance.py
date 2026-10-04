"""Equality in a constraint is tolerant, not exact.

Operands are normalized currency/number values that arrive as floats, so
binary floating point made exact `operator.eq` wrong for the one thing
constraints exist to express. The feature's own headline example reported a
false violation on a CORRECT invoice -- which is worse than no check, because
it trains reviewers to ignore the output.
"""

from unstract.agent_kv_schema import evaluate_constraints

# Three identical line items. 8230.4 * 3 is 24691.199999999997 in binary
# floating point, so `sum(...) == 24691.2` was False and the constraint was
# reported violated.
_ROWS = {"line_items": [{"line_total": "8230.40"} for _ in range(3)]}


def test_the_headline_example_is_not_a_false_violation():
    violations = evaluate_constraints(
        ["grand_total == sum('line_items.line_total')"],
        {"grand_total": "24691.20"},
        _ROWS,
    )
    assert violations == []


def test_a_real_mismatch_is_still_reported():
    """The tolerance must not swallow genuine errors -- an invoice off by a
    cent is exactly what this check is for.
    """
    violations = evaluate_constraints(
        ["grand_total == sum('line_items.line_total')"],
        {"grand_total": "24691.21"},
        _ROWS,
    )
    assert violations == ["grand_total == sum('line_items.line_total')"]


def test_not_equal_is_the_negation_of_the_tolerant_equality():
    """`!=` must agree with `==`, or a schema author gets both reported."""
    expr = "grand_total != sum('line_items.line_total')"
    assert evaluate_constraints([expr], {"grand_total": "24691.20"}, _ROWS) == [expr]
    assert evaluate_constraints([expr], {"grand_total": "24691.21"}, _ROWS) == []


def test_comparison_against_exact_zero_still_works():
    """Relative tolerance alone is useless at zero -- every non-zero value is
    infinitely far from 0 in relative terms -- which is why abs_tol is also set.
    """
    assert evaluate_constraints(["balance == 0"], {"balance": "0.00"}, {}) == []
    assert evaluate_constraints(["balance == 0"], {"balance": "1.00"}, {}) == [
        "balance == 0"
    ]


def test_ordering_comparisons_stay_exact():
    """Left deliberately exact: a tolerant `<` would make `a < b` and `a == b`
    both true at the boundary, and "a total that is too large" is not a
    rounding artefact.
    """
    assert evaluate_constraints(["total > 100"], {"total": "100.00"}, {}) == [
        "total > 100"
    ]
    assert evaluate_constraints(["total >= 100"], {"total": "100.00"}, {}) == []
