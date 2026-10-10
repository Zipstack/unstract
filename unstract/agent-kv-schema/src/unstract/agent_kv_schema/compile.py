"""Cap-enforcing, syntax-validating wrapper over the ported compiler.

This is the entry point the API uses for submit-time validation. Anything
``compile_schema`` accepts, the engine must execute; anything it rejects never
reaches OCR or an LLM.

It is NOT, despite what this docstring said before, "the single entry point
both the API and the cloud engine use". The engine calls the raw
``kv_schema.compile``/``compile_arrays`` directly (see the import note in the
cloud plugin's ``engine/kv_extractor.py``), so the caps below are enforced on
the submit path only. That is sound while the backend is the sole producer of a
compiled schema -- which it is today -- but it means the caps are a gate, not
an invariant the engine itself re-checks. Anything that ever hands the engine a
schema from another source has to apply them, or this module has to become what
it claimed to be.
"""

import ast
import re
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
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.UnaryOp,
    ast.Not,
    ast.USub,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.BinOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Constant,
    ast.Load,
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
                f"constraint uses disallowed syntax ({type(node).__name__}): {expr!r}"
            )
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_CALLS:
                raise SchemaError(f"constraint calls a disallowed function: {expr!r}")
            if (
                node.keywords
                or len(node.args) != 1
                or not isinstance(node.args[0], ast.Constant)
                or not isinstance(node.args[0].value, str)
            ):
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


# Quantified groups that themselves contain a quantifier, e.g. `(a+)+`, `(a*)*`,
# `(.+)*`, `(?:x+)+`. This is the shape behind catastrophic backtracking.
_NESTED_QUANTIFIER = re.compile(
    r"\((?:\?[:=!]|\?<[=!]|\?P<[^>]+>)?"  # group open, incl. non-capturing/named
    r"[^()]*[+*}]\??"  # ...containing a quantifier
    r"[^()]*\)"  # ...group close
    r"\s*[+*]|\)\s*\{\d+,\d*\}"  # ...itself quantified
)


# A quantified group whose alternatives OVERLAP, e.g. `(a|aa)+`. Found in
# review after the nested-quantifier check shipped: `^(a|aa)+$` passes that
# check and still backtracks catastrophically, because at each position the
# engine can consume one `a` or two and must try both on failure.
#
# Only LITERAL branches are compared, and only by the prefix relation: if one
# branch is a prefix of another (`a` of `aa`), the group is ambiguous and
# refused. `(foo|bar)+` is left alone -- distinct first characters mean no
# position admits two parses, so it is linear. Branches containing
# metacharacters are not analysed (`.`/classes/nested groups need real regex
# analysis, which is what UN-4225 is for); this closes the demonstrated family
# without pretending to be a decision procedure.
_QUANTIFIED_GROUP = re.compile(r"\((\?:)?([^()]*)\)\s*(?:[+*]|\{\d+,\d*\})")
_LITERAL_BRANCH = re.compile(r"^[\w\-/ ]*$")


def _overlapping_alternation(pattern: str) -> str | None:
    """Return a human-readable overlap if a quantified group is ambiguous."""
    for match in _QUANTIFIED_GROUP.finditer(pattern):
        body = match.group(2)
        if "|" not in body:
            continue
        branches = body.split("|")
        if not all(_LITERAL_BRANCH.match(b) for b in branches):
            continue
        for i, a in enumerate(branches):
            for j, b in enumerate(branches):
                if i != j and a and b.startswith(a):
                    return f"{a!r} is a prefix of {b!r}"
    return None


def _reject_unsafe_regex(path: str, pattern: str) -> None:
    """Refuse an author-supplied pattern at SUBMIT rather than at match time.

    Two separate problems, both found in review:

    1. The pattern was never compiled here, so a syntactically invalid one was
       accepted and only discovered per-value in the engine's QA pass -- where
       ``_check_one`` swallows ``re.error`` and returns True, silently passing
       validation the author thought they had configured.
    2. ``validate_format`` runs the pattern against extracted values with no
       time budget, so a catastrophically-backtracking pattern is a DoS. The
       length cap is NOT a mitigation: ``^(a+)+$`` is 7 characters and takes
       ~1.9s on 26 ``a``s, ~4x per character added (measured), so a 40-char
       value runs for hours. With ``AGENT_KV_CONCURRENT_LIMIT=5`` one org can
       pin five shared worker slots from a single submit.

    The nested-quantifier check is a CONSERVATIVE HEURISTIC, not a proof. It
    rejects the shape responsible for the realistic cases (a quantified group
    whose body is itself quantified) and will reject some safe patterns that
    happen to look like it -- an explicit trade, since the author gets an
    immediate, actionable error instead of a job that hangs. It does not catch
    every pathological pattern; the complete fix is a linear-time engine (RE2),
    which cannot be added here because this package deliberately has zero
    dependencies and is installed by both repos. Tracked as UN-4225.
    """
    try:
        re.compile(pattern)
    except re.error as e:
        raise SchemaError(f"'{path}' has an invalid regex: {e}") from None
    if _NESTED_QUANTIFIER.search(pattern):
        raise SchemaError(
            f"'{path}' regex has a nested quantifier (e.g. '(a+)+'), which can "
            "backtrack catastrophically and stall extraction. Rewrite it "
            "without a quantifier inside a quantified group."
        )
    overlap = _overlapping_alternation(pattern)
    if overlap:
        raise SchemaError(
            f"'{path}' regex quantifies a group whose alternatives overlap "
            f"({overlap}), e.g. '(a|aa)+', which can backtrack "
            "catastrophically and stall extraction. Make the alternatives "
            "mutually exclusive, or use a character class."
        )


#: The formats ``validators._check_one`` actually implements. Anything else is
#: passed through as a free-text LLM hint, which is deliberate (see the
#: ``format`` comment on ``KeySpec``) -- and is also why a typo in one of these
#: six is invisible: ``format: "Number"`` is not a known format, so it becomes a
#: hint, so ``validate_format`` returns True for every value forever and
#: ``/validate`` reports ``{"valid": true}``. The author configured validation
#: and got none, with no error anywhere to find it by.
_KNOWN_FORMATS = frozenset({"string", "number", "date", "currency", "enum", "regex"})


def _reject_unusable_formats(key_specs, array_specs) -> None:
    """Refuse declared formats that can never validate anything, or always fail.

    Four shapes, all accepted before review and all verified by execution:

    * ``format: "Number"`` -- a case variant of a known format. Silently
      degrades to a free-text hint, disabling validation for that key. Rejected
      with the intended spelling, rather than guessed at: a schema author who
      meant the hint can lower-case it or reword it, and one who meant the
      format gets told.
    * ``format: "Enum:paid,unpaid"`` / ``"REGEX:^[0-9]+$"`` -- the same defect
      class for the two formats that take an ARGUMENT, and the one the first
      round's fix missed. ``_parse_format`` matches the ``enum:`` / ``regex:``
      prefix case-sensitively, so these never reach kind ``"enum"``/``"regex"``;
      they arrive as the whole raw string, which no bare-name comparison
      matches. Validation was silently off for the key -- the precise outcome
      the first bullet exists to prevent, reached by a route it did not cover.
    * ``format: "enum:"`` -- no values, so ``_check_one`` tests membership of
      the empty set and EVERY non-empty value fails QA for the life of the job.
    * ``format: "regex:"`` -- empty pattern, so ``re.fullmatch("", v)`` matches
      nothing but the empty string, which ``validate_format`` already passes
      before reaching the pattern. Same outcome: nothing can ever conform.

    The last two are worse than the first: they do not disable validation, they
    invert it, and the result is a document that fails QA no matter what is on
    the page.
    """
    for kspec in _every_leaf(key_specs, array_specs):
        fmt = kspec.format
        lowered = fmt.casefold()
        # `lowered` catches a bare case variant (`"Number"`). `kind_only`
        # catches the two formats that take an ARGUMENT, which the bare check
        # misses entirely: `_parse_format` matches the `enum:` / `regex:`
        # prefix case-SENSITIVELY, so `"Enum:paid,unpaid"` never becomes kind
        # `"enum"` -- it arrives here as the whole raw string, and
        # `"enum:paid,unpaid".casefold()` is not a member of `_KNOWN_FORMATS`
        # (which holds the bare `"enum"`). So the mis-cased form slipped this
        # guard, parsed as a free-text kind, and validation was silently off
        # for that key -- exactly the failure this function closes for bare
        # formats.
        #
        # Splitting on the colon is safe for genuine free text: a hint like
        # `"customer:id"` yields `"customer"`, which is not a known format.
        #
        # Rejected rather than auto-corrected, to match the bare case above: a
        # schema author who meant the format gets told the spelling, and one
        # who meant a free-text hint can reword it. Silently honouring `Enum:`
        # would make case significant in one direction only.
        kind_only = lowered.split(":", 1)[0]
        if fmt not in _KNOWN_FORMATS and (
            lowered in _KNOWN_FORMATS or kind_only in _KNOWN_FORMATS
        ):
            raise SchemaError(
                f"'{kspec.path}' declares format {fmt!r}, which is not a known "
                f"format and is therefore treated as free text -- no validation "
                f"would run. Did you mean {lowered!r}?"
            )
        if fmt == "enum" and not kspec.enum_values:
            raise SchemaError(
                f"'{kspec.path}' declares an enum with no values "
                f"(e.g. 'enum:paid,unpaid'); as written no value can ever conform."
            )
        if fmt == "regex" and not kspec.regex_pattern:
            raise SchemaError(
                f"'{kspec.path}' declares an empty regex; as written no value "
                f"can ever conform."
            )


def _reject_unknown_key_columns(array_specs) -> None:
    """Refuse an array's ``_key`` that names a column the array does not declare.

    ``key_column`` selects row identity for scoring. A name with no matching
    column is not an error anywhere downstream -- every row simply misses, and
    the array silently falls back to positional identity. So a typo costs
    accuracy on exactly the arrays the author cared enough about to key, and
    reports nothing.
    """
    for aspec in array_specs:
        if not aspec.key_column:
            continue  # '' is the documented "positional identity" default
        columns = {s.path for s in aspec.item_specs}
        if aspec.key_column not in columns:
            raise SchemaError(
                f"array '{aspec.path}' declares _key "
                f"{aspec.key_column!r}, which is not one of its columns "
                f"({sorted(columns)})."
            )


def _every_leaf(key_specs, array_specs):
    """Scalar leaves and array columns, which carry the same per-leaf rules."""
    return list(key_specs) + [s for a in array_specs for s in a.item_specs]


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

    _enforce_shape_caps(key_specs, array_specs, caps)
    _enforce_leaf_caps(key_specs, array_specs, caps)
    _reject_unusable_formats(key_specs, array_specs)
    _reject_unknown_key_columns(array_specs)
    constraints = _validated_constraints(spec, caps)

    return CompiledSchema(
        key_specs=key_specs, array_specs=array_specs, constraints=list(constraints)
    )


def _enforce_shape_caps(key_specs, array_specs, caps: SchemaCaps) -> None:
    """Bound how much structure the schema declares."""
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


def _enforce_leaf_caps(key_specs, array_specs, caps: SchemaCaps) -> None:
    """Bound every leaf's author-supplied text, across scalars and array columns."""
    for kspec in _every_leaf(key_specs, array_specs):
        _reject_unsafe_regex(kspec.path, kspec.regex_pattern)
        if len(kspec.regex_pattern) > caps.max_regex_len:
            raise SchemaError(
                f"'{kspec.path}' regex exceeds max_regex_len={caps.max_regex_len}"
            )
        if len(kspec.aliases) > caps.max_aliases:
            raise SchemaError(f"'{kspec.path}' exceeds max_aliases={caps.max_aliases}")
        if len(kspec.effective_description) > caps.max_description_len:
            raise SchemaError(
                f"'{kspec.path}' description exceeds "
                f"max_description_len={caps.max_description_len}"
            )


def _validated_constraints(spec: dict, caps: SchemaCaps) -> list:
    """Return the schema's `_constraints`, rejecting a malformed or oversized list."""
    constraints = spec.get("_constraints", [])
    if not isinstance(constraints, list) or not all(
        isinstance(c, str) for c in constraints
    ):
        raise SchemaError("_constraints must be a list of strings")
    if len(constraints) > caps.max_constraints:
        raise SchemaError(f"schema exceeds max_constraints={caps.max_constraints}")
    for expr in constraints:
        _check_constraint_syntax(expr)
    return constraints
