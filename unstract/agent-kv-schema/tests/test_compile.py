"""compile_schema: structural validation + caps on top of the ported compiler."""
import pytest

from unstract.agent_kv_schema import (
    CompiledSchema, SchemaCaps, SchemaError, compile_schema,
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
    with pytest.raises(SchemaError, match="max_leaves"):
        compile_schema(spec, caps=SchemaCaps(max_leaves=4))


def test_depth_cap_enforced():
    spec = {"a": {"b": {"c": {"d": {"description": "deep"}}}}}
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(spec, caps=SchemaCaps(max_depth=3))


def test_regex_length_cap():
    spec = {"a": {"description": "d", "format": "regex:" + "x" * 300}}
    with pytest.raises(SchemaError, match="max_regex_len"):
        compile_schema(spec)


def test_bad_constraint_syntax_rejected():
    spec = {"a": {"description": "d"},
            "_constraints": ["__import__('os').system('true')"]}
    with pytest.raises(SchemaError, match="constraint"):
        compile_schema(spec)


def test_constraint_call_allowlist():
    spec = {"a": {"description": "d"}, "_constraints": ["foo('a.b') > 1"]}
    with pytest.raises(SchemaError, match="constraint"):
        compile_schema(spec)


def test_constraints_cap():
    spec = {"a": {"description": "d"},
            "_constraints": ["a > 0"] * 31}
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
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(_nest(30), caps=SchemaCaps(max_depth=6))


def test_decoy_array_key_cannot_bypass_depth_cap():
    # A top-level field literally named "_array" short-circuited the old
    # depth walk (`if "_array" in node: return depth + 1`), so its real
    # nesting was never counted. The compiler treats "_array" as a plain
    # field name here (an array NODE is one CONTAINING an `_array` key), so
    # the nesting under it is real -- and must still be capped.
    decoy = {"_array": _nest(30)}
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(decoy, caps=SchemaCaps(max_depth=6))


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
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema(_nest(5000), caps=SchemaCaps(max_depth=6))


def test_pathologically_deep_under_decoy_array_raises_fast():
    # Same DoS but hidden under a decoy `_array` key so the compile.py depth
    # pre-check short-circuits -- the guard inside the real recursive walk
    # (`kv_schema._walk`) must still catch it as SchemaError, not
    # RecursionError.
    with pytest.raises(SchemaError, match="max_depth"):
        compile_schema({"_array": _nest(5000)}, caps=SchemaCaps(max_depth=6))
