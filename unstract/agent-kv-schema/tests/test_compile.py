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
