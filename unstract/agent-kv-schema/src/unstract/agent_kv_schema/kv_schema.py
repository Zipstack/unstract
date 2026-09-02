"""Compile a user-authored nested key schema into a flat, ordered KeySpec list,
and reassemble flat extracted values back into the nested shape.

Leaf/interior rule (spec §7): a node is INTERIOR iff ALL of its values are objects
(its keys are child nodes); otherwise it is a LEAF defined by its scalar attributes.
A node mixing object and scalar values is a compile-time error. Reserved attribute
words cannot be used as child-node key names.
"""
from typing import Any, Dict, List

from .dataclasses import KeySpec, ArraySpec

RESERVED = {"description", "format", "required", "aliases", "multivalued"}
RESERVED_NODE = {"_array", "description", "_key"}   # node-level (distinct from leaf-attr RESERVED)

# Absolute structural-depth ceiling for callers that don't pass an explicit
# max_depth (the public compile/compile_arrays entry points). It only has to
# sit well below Python's ~1000 recursion limit so a hostile keys.json fails
# fast as a clean ValueError (-> SchemaError) instead of a RecursionError;
# compile_schema always passes the real, much smaller cap from SchemaCaps.
_DEFAULT_MAX_DEPTH = 100


def _parse_format(raw: str):
    """Return (kind, enum_values, regex_pattern) for a declared format string."""
    if raw.startswith("enum:"):
        values = [v.strip() for v in raw[len("enum:"):].split(",") if v.strip()]
        return "enum", values, ""
    if raw.startswith("regex:"):
        return "regex", [], raw[len("regex:"):]
    return raw, [], ""


def _walk(node: Dict[str, Any], path_parts: List[str], out: List[KeySpec],
          arrays: List[ArraySpec], *, max_depth: int = _DEFAULT_MAX_DEPTH,
          depth: int = 0) -> None:
    # HARD structural-depth ceiling at the TOP of the recursive walk. This is
    # the real backstop the compile.py `_max_depth` pre-check can't provide:
    # that check treats array columns as row-local (not nesting) and is blind
    # to a decoy top-level `_array` field's real nesting, so a schema can pass
    # it yet still recurse arbitrarily deep here. `depth` increments on EVERY
    # recursion (interior children AND array columns), so exceeding the cap
    # raises a clean ValueError -- surfaced as SchemaError by compile_schema --
    # instead of an uncaught RecursionError.
    if depth > max_depth:
        raise ValueError(f"schema exceeds max_depth={max_depth}")
    if not isinstance(node, dict) or not node:
        raise ValueError(f"Schema node at {'.'.join(path_parts) or '<root>'} must be a non-empty object")

    if "_array" in node:
        extra = set(node.keys()) - RESERVED_NODE
        if extra:
            raise ValueError(
                f"Array node at {'.'.join(path_parts) or '<root>'} has unexpected keys {sorted(extra)}; "
                f"allowed: {sorted(RESERVED_NODE)}")
        item_schema = node["_array"]
        if not isinstance(item_schema, dict) or not item_schema:
            raise ValueError(f"Array item schema at {'.'.join(path_parts)} must be a non-empty object")
        item_specs: List[KeySpec] = []
        for col_name, col_node in item_schema.items():
            if isinstance(col_node, dict) and "_array" in col_node:
                raise ValueError(f"Nested array at {'.'.join(path_parts)}.{col_name} is P8b (not supported in P8a)")
            _walk(col_node, [col_name], item_specs, [],   # row-LOCAL paths; nested arrays sink to [] (rejected above)
                  max_depth=max_depth, depth=depth + 1)
        arrays.append(ArraySpec(path=".".join(path_parts), description=str(node.get("description", "")),
                                item_specs=item_specs, key_column=str(node.get("_key", ""))))
        return

    object_values = [v for v in node.values() if isinstance(v, dict)]
    scalar_keys = [k for k, v in node.items() if not isinstance(v, dict)]

    is_interior = len(object_values) == len(node)   # every value is an object
    is_leaf = len(object_values) == 0               # no value is an object

    if not is_interior and not is_leaf:
        raise ValueError(
            f"Schema node at {'.'.join(path_parts) or '<root>'} mixes object children "
            f"and scalar attributes; an interior node's values must all be objects"
        )

    if is_interior:
        for child_name, child_node in node.items():
            _walk(child_node, path_parts + [child_name], out, arrays,
                  max_depth=max_depth, depth=depth + 1)
        return

    # Leaf node: scalar attributes only.
    unknown = [k for k in scalar_keys if k not in RESERVED]
    if unknown:
        raise ValueError(
            f"Leaf at {'.'.join(path_parts)} has unknown attribute(s) {unknown}; "
            f"allowed: {sorted(RESERVED)}"
        )
    if "description" not in node:
        raise ValueError(f"Leaf at {'.'.join(path_parts)} is missing a 'description'")

    kind, enum_values, regex_pattern = _parse_format(str(node.get("format", "string")))
    breadcrumb = " > ".join(path_parts)
    out.append(KeySpec(
        path=".".join(path_parts),
        effective_description=f"{breadcrumb}: {node['description']}",
        format=kind,
        enum_values=enum_values,
        regex_pattern=regex_pattern,
        required=bool(node.get("required", False)),
        aliases=list(node.get("aliases", [])),
        multivalued=bool(node.get("multivalued", False)),
    ))


def _compile_both(spec_json: Dict[str, Any], max_depth: int = _DEFAULT_MAX_DEPTH):
    if not isinstance(spec_json, dict):
        raise ValueError("Top-level key schema must be a JSON object")
    out: List[KeySpec] = []
    arrays: List[ArraySpec] = []
    for top_name, top_node in spec_json.items():
        if top_name == "_constraints":
            continue
        _walk(top_node, [top_name], out, arrays, max_depth=max_depth)
    return out, arrays


def compile(spec_json: Dict[str, Any], max_depth: int = _DEFAULT_MAX_DEPTH) -> List[KeySpec]:
    """Compile to an ordered flat list of SCALAR leaf KeySpecs (array nodes excluded)."""
    return _compile_both(spec_json, max_depth)[0]


def compile_arrays(spec_json: Dict[str, Any], max_depth: int = _DEFAULT_MAX_DEPTH) -> List[ArraySpec]:
    """Compile the top-level/interior-nested array nodes to an ordered list of ArraySpecs."""
    return _compile_both(spec_json, max_depth)[1]


def reassemble(values: Dict[str, Any], specs: List[KeySpec],
               arrays: List[ArraySpec] = None, array_values: Dict[str, Any] = None) -> Dict[str, Any]:
    """Rebuild the nested dict from flat {dotted_path: value}.

    Iterates `specs` (so output key order follows the schema) and places each
    present value at its dotted path. Multi-valued leaves are comma-separated
    strings and pass through verbatim. Paths absent from `values` are skipped.

    Arrays (P8a): for each ArraySpec in `arrays`, place its pre-rendered
    list-of-dicts (from `array_values[path]`) at its dotted path. Scalar-only
    callers (arrays/array_values=None) behave identically to before.
    """
    out: Dict[str, Any] = {}
    for spec in specs:
        if spec.path not in values:
            continue
        parts = spec.path.split(".")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = values[spec.path]
    for aspec in (arrays or []):
        rows = (array_values or {}).get(aspec.path)
        if rows is None:
            continue
        parts = aspec.path.split(".")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = rows   # list-of-dicts
    return out
