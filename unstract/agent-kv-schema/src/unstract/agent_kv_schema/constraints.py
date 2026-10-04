"""Cross-field consistency (spec §18.3): a fail-closed evaluator for schema-author-declared
constraints over the NORMALIZED key values. No eval/exec — a static AST allowlist (Compare/BoolOp/
BinOp/UnaryOp/Name/Attribute-path/Constant only). Operands resolve to normalized values; a missing/
empty/un-coercible operand SKIPS the constraint (advisory), never crashes. Returns violated exprs.
"""

import ast
import math
import operator

from .validators import coerce_number

# Equality on these values is TOLERANT, not exact. Operands are normalized
# currency/number values that arrived as floats, so binary floating point makes
# exact `==` wrong for the thing constraints exist to express. The feature's own
# headline example reports a false violation on a CORRECT invoice:
# three line items of 8230.4 sum to 24691.199999999997, which `operator.eq`
# says is not 24691.2 (reproduced).
#
# The tolerance has to sit BELOW a cent at every realistic magnitude while
# staying ABOVE the float noise floor. Those two bounds are what set the
# numbers, and the first attempt at this got it wrong: `rel_tol=1e-9` is 0.1 at
# a total of $100,000,000, so it silently absorbed a one-cent reconciliation
# error on a large invoice -- the exact failure this check exists to catch
# (found in review; the original test only covered a ~$25,000 total).
#
# Noise floor: summing N values of magnitude M accumulates roughly
# N * 2.2e-16 * M of float error. M=$1e8 over 1,000 rows is ~2.2e-5, i.e. about
# a five-hundredth of a cent.
#
#   rel_tol=1e-12  -> 1e-4 at $1e8 (a hundredth of a cent): absorbs that noise,
#                     and a one-cent error is 100x larger, so it is still
#                     reported. Relative rather than absolute-only so the bound
#                     tracks magnitude -- an absolute epsilon suited to invoice
#                     totals is meaningless against unit prices in thousandths.
#   abs_tol=1e-6   -> keeps comparisons against exact zero working, where
#                     relative tolerance is useless (every non-zero value is
#                     infinitely far from 0 in relative terms), and is itself
#                     well under a cent.
#
# Known ceiling: past ~$1e12 with ~10,000 rows the noise floor (~2.2) exceeds a
# cent and no float tolerance can separate the two. That is a float problem,
# not a tolerance problem, and the fix is Decimal end to end --
# `normalizers.coerce_number`, UN-4226. This makes the COMPARISON correct for
# the float values that exist today, and stays correct afterwards.
_REL_TOL = 1e-12
_ABS_TOL = 1e-6


def _num_eq(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=_ABS_TOL)
    return operator.eq(a, b)


def _num_ne(a, b) -> bool:
    return not _num_eq(a, b)


_CMP = {
    ast.Eq: _num_eq,
    ast.NotEq: _num_ne,
    # Ordering comparisons are left exact on purpose: a tolerant `<` would make
    # `a < b` and `a == b` both true at the boundary, and the failure mode these
    # express (a total that is too large/small) is not a rounding artefact.
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}
_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}

# P8c: the ONLY callable names permitted in a constraint, and only over a single
# string-literal `'array_path'` / `'array_path.column'` argument. This is NOT a general
# function-call capability — it is a closed allowlist of pure numeric reductions evaluated
# in Python (never via eval/exec) so a scalar key can be reconciled against an array column
# (e.g. grand_total == sum('line_items.line_total')).
_AGG = {"sum", "count", "min", "max", "avg"}


class _Skip(Exception):
    """Operand missing/empty/incomparable — skip this constraint (advisory)."""


def _path(node) -> str:
    """Reconstruct a dotted path from a Name / Attribute-chain (pure attribute access only)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_path(node.value)}.{node.attr}"
    raise _Skip()


def _coerce(raw: str):
    """Normalized value -> finite float when numeric, else the string (ISO dates compare
    lexicographically). Uses the canonical coercer so thousands-separated values ('9,000')
    parse numerically (a bare float() would leave them as strings and silently drop a real
    violation via the like-type guard); 'nan'/'inf' tokens stay strings (not comparable numbers).
    """
    n = coerce_number(
        raw
    )  # strips commas/$/%; returns None for non-numeric AND non-finite
    return n if n is not None else raw


def _aggregate(node: ast.Call, arrays: dict[str, list[dict[str, str]]]):
    """Evaluate one of the five allowlisted aggregates over an array column.

    FAIL-CLOSED by construction: the only thing this accepts is `NAME('literal')` where
    NAME is in `_AGG`, the func is a bare ast.Name (no attribute access — blocks
    `os.system`/`x.__class__`), there is exactly one positional arg, no keywords, and that
    arg is a string Constant. Any deviation raises `_Skip` (-> constraint skipped, never run).

    Argument is `'array_path'` (only valid for count = row count) or `'array_path.column'`.
    Numeric cells (sum/min/max/avg) are pulled with the SAME `coerce_number` used elsewhere
    (strips commas/$/%, drops non-finite/empty -> None); such cells are skipped (not zeroed).
    `count('a.col')` counts rows whose column value is NON-EMPTY (text columns like
    sku/description count too); `count('a')` is the row count. A sum/min/max/avg over zero
    usable cells raises `_Skip` (advisory) rather than guessing 0.
    """
    if not isinstance(node.func, ast.Name) or node.func.id not in _AGG:
        raise _Skip()  # not a whitelisted aggregate name
    if node.keywords or len(node.args) != 1:
        raise _Skip()  # exactly one positional arg, no keywords
    arg = node.args[0]
    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
        raise _Skip()  # arg must be a literal string path
    fn, ref = node.func.id, arg.value
    # Split on the LAST dot: an ArraySpec.path may itself be dotted (e.g. 'invoice.lines'),
    # while the column is always a row-LOCAL bare name. A bare ref (no dot) is a whole-array
    # row count -> array_path=ref, column=''.
    if "." in ref:
        array_path, _, column = ref.rpartition(".")
    else:
        array_path, column = ref, ""
    rows = arrays.get(array_path)
    if rows is None:  # no such array available
        raise _Skip()

    if fn == "count":
        if not column:  # count('array') -> number of rows
            return float(len(rows))
        # count('array.col') -> rows with a non-empty value for that column (text columns
        # like sku/description/name are valid to count; numeric coercion would zero them out)
        return float(sum(1 for r in rows if (r.get(column) or "").strip() != ""))

    if not column:  # sum/min/max/avg need a column
        raise _Skip()
    nums = [n for r in rows if (n := coerce_number(r.get(column))) is not None]
    if not nums:  # nothing usable -> advisory skip
        raise _Skip()
    if fn == "sum":
        return float(sum(nums))
    if fn == "min":
        return float(min(nums))
    if fn == "max":
        return float(max(nums))
    return float(sum(nums) / len(nums))  # avg


def _operand(node, values: dict[str, str], arrays: dict[str, list[dict[str, str]]]):
    if isinstance(node, ast.Call):
        return _aggregate(node, arrays)  # ONLY the _AGG allowlist; else _Skip
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        a, b = _operand(node.left, values, arrays), _operand(node.right, values, arrays)
        if not (isinstance(a, (int, float)) and isinstance(b, (int, float))):
            raise _Skip()
        return _BIN[type(node.op)](a, b)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _operand(node.operand, values, arrays)
        if not isinstance(v, (int, float)):
            raise _Skip()
        return -v
    # else: a key reference
    path = _path(node)
    raw = values.get(path)
    if raw is None or raw == "":
        raise _Skip()
    return _coerce(raw)


def _truth(node, values: dict[str, str], arrays: dict[str, list[dict[str, str]]]) -> bool:
    if isinstance(node, ast.BoolOp):
        sub = [_truth(v, values, arrays) for v in node.values]
        return all(sub) if isinstance(node.op, ast.And) else any(sub)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _truth(node.operand, values, arrays)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators):
        left = _operand(node.left, values, arrays)
        for op, comp in zip(node.ops, node.comparators, strict=False):
            if type(op) not in _CMP:
                raise _Skip()
            right = _operand(comp, values, arrays)
            # only compare like-typed operands (number<->number, str<->str); else skip
            if isinstance(left, (int, float)) != isinstance(right, (int, float)):
                raise _Skip()
            if not _CMP[type(op)](left, right):
                return False
            left = right
        return True
    raise _Skip()


def _evaluate_one(
    expr: str, values: dict[str, str], arrays: dict[str, list[dict[str, str]]]
):
    """Return True/False, or None to skip (missing operand / unsupported / unsafe)."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError:
        return None
    try:
        return _truth(tree.body, values, arrays)
    except _Skip:
        return None
    except Exception:
        return None  # fail-closed: any surprise -> skip, never crash the pipeline


def evaluate_constraints(
    constraints: list[str],
    values: dict[str, str],
    arrays: dict[str, list[dict[str, str]]] | None = None,
) -> list[str]:
    """Return the list of constraint expressions that evaluated to False (violations).
    Skipped (missing operand / unsupported / unsafe) constraints are NOT violations.

    `arrays` (optional) maps an ArraySpec path to its rendered rows (list of {column: value})
    so the five allowlisted aggregates (sum/count/min/max/avg) can reconcile a scalar key
    against an array column. Defaults to {} -> aggregates become no-op skips (back-compat).
    """
    arrays = arrays or {}
    violations = []
    for expr in constraints or []:
        if _evaluate_one(expr, values, arrays) is False:
            violations.append(expr)
    return violations
