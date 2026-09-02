"""Cap-enforcing, syntax-validating wrapper over the ported compiler.

This is the single entry point both the API (submit-time validation) and the
cloud engine use. Anything compile_schema accepts, the engine must execute;
anything it rejects never reaches OCR or an LLM.
"""
import ast
from dataclasses import dataclass, field

from . import kv_schema
from .dataclasses import ArraySpec, KeySpec


class SchemaError(ValueError):
    """User-facing schema rejection; message is safe to return in a 400."""


@dataclass(frozen=True)
class SchemaCaps:
    max_leaves: int = 200
    max_arrays: int = 20
    max_columns_per_array: int = 40
    max_depth: int = 6
    max_regex_len: int = 200
    max_aliases: int = 10
    max_description_len: int = 500
    max_constraints: int = 30


@dataclass(frozen=True)
class CompiledSchema:
    key_specs: list[KeySpec] = field(default_factory=list)
    array_specs: list[ArraySpec] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


_ALLOWED_CALLS = {"sum", "count", "min", "max", "avg"}
_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Call, ast.Name, ast.Attribute, ast.Constant, ast.Load,
)


def _check_constraint_syntax(expr: str) -> None:
    """Static allowlist mirroring constraints._evaluate_one's grammar."""
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise SchemaError(f"constraint does not parse: {expr!r} ({e.msg})") from e
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise SchemaError(
                f"constraint uses disallowed syntax "
                f"({type(node).__name__}): {expr!r}"
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                raise SchemaError(f"constraint calls a disallowed function: {expr!r}")
            if node.keywords or len(node.args) != 1 or not isinstance(
                node.args[0], ast.Constant
            ) or not isinstance(node.args[0].value, str):
                raise SchemaError(
                    f"constraint aggregate needs one string literal arg: {expr!r}"
                )


def _max_depth(node: object, max_depth: int, depth: int = 0) -> int:
    # HARD ceiling FIRST -- before the `_array` short-circuit and before any
    # further recursion. Two bugs this closes: (a) a pathologically deep plain
    # schema (256 KiB of JSON nests ~40k deep, far past Python's ~1000
    # recursion limit) used to raise an uncaught RecursionError (500) here;
    # now it fails fast as a clean SchemaError (400). (b) The `_array`
    # short-circuit below cannot be reached to bypass the cap once `depth`
    # has already blown past it.
    if depth > max_depth:
        raise SchemaError(f"schema exceeds max_depth={max_depth}")
    if not isinstance(node, dict):
        return depth
    if "_array" in node:
        return depth + 1  # array columns are row-local, not nesting
    child = [v for v in node.values() if isinstance(v, dict)]
    if not child:
        return depth + 1
    return max(_max_depth(v, max_depth, depth + 1) for v in child)


def compile_schema(spec: dict, caps: SchemaCaps | None = None) -> CompiledSchema:
    caps = caps or SchemaCaps()
    if not isinstance(spec, dict):
        raise SchemaError("Top-level key schema must be a JSON object")
    cleaned = {k: v for k, v in spec.items() if k != "_constraints"}
    if _max_depth(cleaned, caps.max_depth) > caps.max_depth:
        raise SchemaError(f"schema exceeds max_depth={caps.max_depth}")
    # The compile.py `_max_depth` pre-check does not count array-column
    # nesting (arrays are row-local there, by design) and cannot see a decoy
    # top-level `_array` field's real nesting -- so the actual recursive walk
    # (`kv_schema._walk`) carries its own max_depth ceiling too, both to close
    # that bypass and to guarantee a clean SchemaError instead of an uncaught
    # RecursionError on a deeply-nested input.
    try:
        key_specs = kv_schema.compile(spec, max_depth=caps.max_depth)
        array_specs = kv_schema.compile_arrays(spec, max_depth=caps.max_depth)
    except ValueError as e:
        raise SchemaError(str(e)) from e

    if len(key_specs) > caps.max_leaves:
        raise SchemaError(f"schema exceeds max_leaves={caps.max_leaves}")
    if len(array_specs) > caps.max_arrays:
        raise SchemaError(f"schema exceeds max_arrays={caps.max_arrays}")
    for aspec in array_specs:
        if len(aspec.item_specs) > caps.max_columns_per_array:
            raise SchemaError(
                f"array '{aspec.path}' exceeds "
                f"max_columns_per_array={caps.max_columns_per_array}"
            )
    for kspec in key_specs + [s for a in array_specs for s in a.item_specs]:
        if len(kspec.regex_pattern) > caps.max_regex_len:
            raise SchemaError(f"'{kspec.path}' regex exceeds max_regex_len={caps.max_regex_len}")
        if len(kspec.aliases) > caps.max_aliases:
            raise SchemaError(f"'{kspec.path}' exceeds max_aliases={caps.max_aliases}")
        if len(kspec.effective_description) > caps.max_description_len:
            raise SchemaError(
                f"'{kspec.path}' description exceeds "
                f"max_description_len={caps.max_description_len}"
            )

    constraints = spec.get("_constraints", [])
    if not isinstance(constraints, list) or not all(
        isinstance(c, str) for c in constraints
    ):
        raise SchemaError("_constraints must be a list of strings")
    if len(constraints) > caps.max_constraints:
        raise SchemaError(f"schema exceeds max_constraints={caps.max_constraints}")
    for expr in constraints:
        _check_constraint_syntax(expr)

    return CompiledSchema(key_specs=key_specs, array_specs=array_specs,
                          constraints=list(constraints))
