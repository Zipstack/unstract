"""compile_schema: structural validation + caps on top of the ported compiler."""

import pytest

from unstract.agent_kv_schema import (
    CompiledSchema,
    SchemaCaps,
    SchemaError,
    compile_schema,
)

VALID = {
    "quotation_number": {"description": "The quote number", "required": True},
    "customer": {"name": {"description": "Bill-to name"}},
    "line_items": {
        "description": "One row per line",
        "_key": "sku",
        "_array": {
            "sku": {"description": "SKU"},
            "total": {"description": "Line total", "format": "currency"},
        },
    },
    "_constraints": ["count('line_items') >= 1"],
}


def test_valid_schema_compiles():
    out = compile_schema(VALID)
    assert isinstance(out, CompiledSchema)
    assert [s.path for s in out.key_specs] == ["quotation_number", "customer.name"]
    assert out.array_specs[0].path == "line_items"
    assert out.constraints == ["count('line_items') >= 1"]


def test_missing_description_is_schema_error():
    with pytest.raises(SchemaError, match="missing a 'description'"):
        compile_schema({"a": {"format": "string"}})


def test_mixed_node_is_schema_error():
    with pytest.raises(SchemaError, match="mixes object children"):
        compile_schema({"a": {"description": "x", "b": {"description": "y"}}})


def test_leaf_cap_enforced():
    spec = {f"k{i}": {"description": "d"} for i in range(5)}
    caps = SchemaCaps(max_leaves=4)
    with pytest.raises(SchemaError, match="max_leaves"):
        compile_schema(spec, caps=caps)


def test_depth_cap_enforced():
    spec = {"a": {"b": {"c": {"d": {"description": "deep"}}}}}
    caps = SchemaCaps(max_depth=3)
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(spec, caps=caps)


def test_regex_length_cap():
    spec = {"a": {"description": "d", "format": "regex:" + "x" * 300}}
    with pytest.raises(SchemaError, match="max_regex_len"):
        compile_schema(spec)


def test_bad_constraint_syntax_rejected():
    spec = {
        "a": {"description": "d"},
        "_constraints": ["__import__('os').system('true')"],
    }
    with pytest.raises(SchemaError, match="constraint"):
        compile_schema(spec)


def test_constraint_call_allowlist():
    spec = {"a": {"description": "d"}, "_constraints": ["foo('a.b') > 1"]}
    with pytest.raises(SchemaError, match="constraint"):
        compile_schema(spec)


def test_constraints_cap():
    spec = {"a": {"description": "d"}, "_constraints": ["a > 0"] * 31}
    with pytest.raises(SchemaError, match="max_constraints"):
        compile_schema(spec)


def test_non_dict_top_level_rejected():
    with pytest.raises(SchemaError):
        compile_schema(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# Depth-cap bypass + unbounded-recursion DoS (pre-Greptile critical #2).
# ---------------------------------------------------------------------------


def _nest(levels: int) -> dict:
    """Build a plain interior schema `levels` deep ending in a leaf."""
    node = {"description": "deep"}
    for i in range(levels):
        node = {f"l{i}": node}
    return node


def test_deeply_nested_raises_schema_error_not_recursion_error():
    # Well past max_depth but nowhere near Python's recursion limit: must be a
    # clean SchemaError (400), never accepted.
    deep, caps = _nest(30), SchemaCaps(max_depth=6)
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(deep, caps=caps)


def test_decoy_array_key_cannot_bypass_depth_cap():
    # A top-level field literally named "_array" short-circuited the old
    # depth walk (`if "_array" in node: return depth + 1`), so its real
    # nesting was never counted. The compiler treats "_array" as a plain
    # field name here (an array NODE is one CONTAINING an `_array` key), so
    # the nesting under it is real -- and must still be capped.
    decoy = {"_array": _nest(30)}
    caps = SchemaCaps(max_depth=6)
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(decoy, caps=caps)


def test_valid_array_within_limits_still_compiles():
    # Genuine array-column spec (node CONTAINING `_array`) with shallow
    # columns must still compile -- the ceiling bounds total structural
    # depth, it does not break real arrays.
    spec = {
        "rows": {
            "description": "line items",
            "_array": {
                "sku": {"description": "SKU"},
                "qty": {"description": "Quantity", "format": "number"},
            },
        }
    }
    out = compile_schema(spec, caps=SchemaCaps(max_depth=6))
    assert isinstance(out, CompiledSchema)
    assert out.array_specs[0].path == "rows"
    assert [s.path for s in out.array_specs[0].item_specs] == ["sku", "qty"]


def test_pathologically_deep_raises_fast_no_recursion_error():
    # ~5000 levels: 256 KiB of JSON nests far past Python's ~1000 recursion
    # limit, so the OLD code raised an uncaught RecursionError (500). Must be
    # a clean, fast SchemaError instead.
    deep, caps = _nest(5000), SchemaCaps(max_depth=6)
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(deep, caps=caps)


def test_pathologically_deep_under_decoy_array_raises_fast():
    # Same DoS but hidden under a decoy `_array` key so the compile.py depth
    # pre-check short-circuits -- the guard inside the real recursive walk
    # (`kv_schema._walk`) must still catch it as SchemaError, not
    # RecursionError.
    decoy, caps = {"_array": _nest(5000)}, SchemaCaps(max_depth=6)
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(decoy, caps=caps)


# ---------------------------------------------------------------------------
# Author-supplied regex is refused at SUBMIT, not discovered at match time.
#
# Two defects, both found in review:
#  1. The pattern was never compiled here, so an invalid one was accepted and
#     only hit per-value in the engine's QA pass -- where `_check_one` swallows
#     `re.error` and returns True, silently passing validation the author
#     thought they had configured.
#  2. `validate_format` runs the pattern with no time budget, so catastrophic
#     backtracking is a DoS. The length cap is NOT a mitigation: `^(a+)+$` is 7
#     characters and takes ~1.9s against 26 `a`s, ~4x per character added
#     (measured on this code), so a 40-char value runs for hours -- and
#     AGENT_KV_CONCURRENT_LIMIT=5 lets one org pin five shared worker slots
#     from a single submit.
#
# The detector is a conservative heuristic, not a proof: it rejects the shape
# behind the realistic cases (a quantifier inside a quantified group). The
# complete fix is a linear-time engine (RE2), which cannot live here because
# this package deliberately has zero dependencies -- UN-4225.
# ---------------------------------------------------------------------------


def _schema(pattern: str) -> dict:
    return {"amount": {"description": "x", "format": f"regex:{pattern}"}}


@pytest.mark.parametrize(
    "pattern",
    [
        "^(a+)+$",  # the classic
        "^(a*)*$",
        "(?:x+)+",  # non-capturing group is not an escape hatch
        "^(a+){2,}$",  # counted repetition of a quantified group
    ],
)
def test_nested_quantifier_is_refused_at_compile(pattern):
    spec = _schema(pattern)
    with pytest.raises(SchemaError, match="nested quantifier"):
        compile_schema(spec)


def test_invalid_regex_is_refused_at_compile_not_swallowed_at_match_time():
    spec = _schema("[")
    with pytest.raises(SchemaError, match="invalid regex"):
        compile_schema(spec)


@pytest.mark.parametrize(
    "pattern",
    [
        r"^\d{3}-\d{4}$",
        r"^[A-Z]{2}\d+$",
        r"^INV-\d+$",
        r"^\$?[\d,]+\.\d{2}$",
    ],
)
def test_ordinary_patterns_still_compile(pattern):
    """The other half of the heuristic's contract. A detector that rejected
    real-world patterns would just push authors off the regex format entirely.
    """
    compiled = compile_schema(_schema(pattern))
    assert compiled.key_specs[0].regex_pattern == pattern


# The overlapping-alternation family, found in review AFTER the
# nested-quantifier check shipped: `^(a|aa)+$` passes that check and still
# backtracks catastrophically, because at each position the engine can consume
# one `a` or two and must try both on failure.
@pytest.mark.parametrize("pattern", ["^(a|aa)+$", "^(a|ab)+$", "(?:x|xx)+"])
def test_overlapping_alternation_is_refused(pattern):
    spec = _schema(pattern)
    with pytest.raises(SchemaError, match="alternatives overlap"):
        compile_schema(spec)


@pytest.mark.parametrize(
    "pattern",
    [
        "^(foo|bar)+$",  # distinct first chars -> no position admits two parses
        r"^(\d|[A-Z])+$",  # metacharacter branches are not analysed
        "^INV-(A|B)+$",
    ],
)
def test_non_overlapping_alternation_still_compiles(pattern):
    """The detector compares only LITERAL branches, by the prefix relation.
    Refusing every quantified alternation would reject a lot of safe, ordinary
    patterns -- `(?:a|b)+` is linear.
    """
    compile_schema(_schema(pattern))
