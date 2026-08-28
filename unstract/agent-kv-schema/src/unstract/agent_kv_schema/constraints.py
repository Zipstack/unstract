"""Cross-field consistency (spec §18.3): a fail-closed evaluator for schema-author-declared
constraints over the NORMALIZED key values. No eval/exec — a static AST allowlist (Compare/BoolOp/
BinOp/UnaryOp/Name/Attribute-path/Constant only). Operands resolve to normalized values; a missing/
empty/un-coercible operand SKIPS the constraint (advisory), never crashes. Returns violated exprs.
"""
import ast
import operator
from typing import Dict, List, Optional

from .validators import coerce_number

_CMP = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

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
    violation via the like-type guard); 'nan'/'inf' tokens stay strings (not comparable numbers)."""
    n = coerce_number(raw)   # strips commas/$/%; returns None for non-numeric AND non-finite
    return n if n is not None else raw


def _aggregate(node: ast.Call, arrays: Dict[str, List[Dict[str, str]]]):
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
        raise _Skip()                                  # not a whitelisted aggregate name
    if node.keywords or len(node.args) != 1:
        raise _Skip()                                  # exactly one positional arg, no keywords
    arg = node.args[0]
    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
        raise _Skip()                                  # arg must be a literal string path
    fn, ref = node.func.id, arg.value
    # Split on the LAST dot: an ArraySpec.path may itself be dotted (e.g. 'invoice.lines'),
    # while the column is always a row-LOCAL bare name. A bare ref (no dot) is a whole-array
    # row count -> array_path=ref, column=''.
    if "." in ref:
        array_path, _, column = ref.rpartition(".")
    else:
        array_path, column = ref, ""
    rows = arrays.get(array_path)
    if rows is None:                                   # no such array available
        raise _Skip()

    if fn == "count":
        if not column:                                 # count('array') -> number of rows
            return float(len(rows))
        # count('array.col') -> rows with a non-empty value for that column (text columns
        # like sku/description/name are valid to count; numeric coercion would zero them out)
        return float(sum(1 for r in rows if (r.get(column) or "").strip() != ""))

    if not column:                                     # sum/min/max/avg need a column
        raise _Skip()
    nums = [n for r in rows if (n := coerce_number(r.get(column))) is not None]
    if not nums:                                       # nothing usable -> advisory skip
        raise _Skip()
    if fn == "sum":
        return float(sum(nums))
    if fn == "min":
        return float(min(nums))
    if fn == "max":
        return float(max(nums))
    return float(sum(nums) / len(nums))                # avg


def _operand(node, values: Dict[str, str], arrays: Dict[str, List[Dict[str, str]]]):
    if isinstance(node, ast.Call):
        return _aggregate(node, arrays)                # ONLY the _AGG allowlist; else _Skip
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


def _truth(node, values: Dict[str, str], arrays: Dict[str, List[Dict[str, str]]]) -> bool:
    if isinstance(node, ast.BoolOp):
        sub = [_truth(v, values, arrays) for v in node.values]
        return all(sub) if isinstance(node.op, ast.And) else any(sub)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _truth(node.operand, values, arrays)
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators):
        left = _operand(node.left, values, arrays)
        for op, comp in zip(node.ops, node.comparators):
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


def _evaluate_one(expr: str, values: Dict[str, str], arrays: Dict[str, List[Dict[str, str]]]):
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


def evaluate_constraints(constraints: List[str], values: Dict[str, str],
                         arrays: Optional[Dict[str, List[Dict[str, str]]]] = None) -> List[str]:
    """Return the list of constraint expressions that evaluated to False (violations).
    Skipped (missing operand / unsupported / unsafe) constraints are NOT violations.

    `arrays` (optional) maps an ArraySpec path to its rendered rows (list of {column: value})
    so the five allowlisted aggregates (sum/count/min/max/avg) can reconcile a scalar key
    against an array column. Defaults to {} -> aggregates become no-op skips (back-compat)."""
    arrays = arrays or {}
    violations = []
    for expr in constraints or []:
        if _evaluate_one(expr, values, arrays) is False:
            violations.append(expr)
    return violations
