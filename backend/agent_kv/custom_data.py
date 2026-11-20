"""`{{custom_data.*}}` substitution for the instruction text a submit carries.

**Resolved at submit, not in the engine.** Both halves of the substitution --
the templates and the data -- arrive in the same request, so a missing key is
knowable before anything is staged, dispatched, slotted or billed. The engines
therefore receive final text and need no knowledge of `custom_data` at all,
which also keeps this testable in the OSS repo where the API lives rather than
in two cloud plugins.

The alternative, resolving engine-side, is what the workflow executor does
(`workers/executor/executors/variable_replacement.py`) and it has to: there the
custom data is attached to a deployment and the prompt to a tool, so neither
side is in the request. Its failure surfaces mid-run on a job the caller has
already paid for. This module deliberately keeps the regex and the dot-path
semantics identical to that one -- a caller must not have to learn two dialects
of the same placeholder -- and differs only in *when* it refuses.

**Where substitution applies, and where it deliberately does not.** Only the
free-text instruction fields: a key's `description`, and the `key_notes`,
`document_class` and `instructions` options. NOT key names and NOT
`json_structure`: both define the shape of the result, so a placeholder there
would let `custom_data` rename the caller's own output fields, and a typo in it
would silently reshape the response rather than fail.
"""

from __future__ import annotations

import re
from typing import Any

#: Identical to `VariableConstants.CUSTOM_DATA_VARIABLE_REGEX` in the workflow
#: executor, wrapped in the `{{ }}` markers that module matches separately.
#: Whitespace inside the braces is tolerated because a hand-written template
#: has it and refusing would be a surprise with no upside.
_PLACEHOLDER = re.compile(r"\{\{\s*custom_data\.([A-Za-z0-9_.]+)\s*\}\}")


class MissingCustomDataKey(KeyError):
    """A template referenced a path `custom_data` does not contain.

    A dedicated type so the caller of this module decides the HTTP shape --
    this module raises, `execution_serializers` turns it into the 400.
    """

    def __init__(self, path: str, *, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(
            f"{{{{custom_data.{path}}}}}: {reason}. Include this key in the "
            "'custom_data' object of your request."
        )


def referenced_paths(text: str) -> list[str]:
    """Every `custom_data` path `text` references, in order, de-duplicated."""
    if not text:
        return []
    seen: dict[str, None] = {}
    for path in _PLACEHOLDER.findall(text):
        seen.setdefault(path, None)
    return list(seen)


def _lookup(custom_data: dict[str, Any] | None, path: str) -> Any:
    if not custom_data:
        # Distinguished from a wrong key on purpose: "you sent no custom_data
        # at all" and "you sent some but not this key" are different mistakes
        # and the fix differs.
        raise MissingCustomDataKey(path, reason="no custom_data was sent with this job")
    value: Any = custom_data
    for part in path.split("."):
        # `value[part]` on a list raises TypeError, on a dict KeyError; both
        # mean the same thing to the caller, matching the executor's handling.
        try:
            value = value[part]
        except (KeyError, TypeError, IndexError) as e:
            raise MissingCustomDataKey(path, reason="key not found in custom_data") from e
    return value


def resolve(text: str, custom_data: dict[str, Any] | None) -> str:
    """Substitute every `{{custom_data.*}}` in `text`.

    A resolved value is stringified, because the destination is prompt text.
    `None` becomes the empty string rather than the literal "None", which is
    what a template author means by an absent optional value -- and is the one
    place this deliberately differs from `str()`.
    """
    if not text:
        return text

    def _sub(match: re.Match[str]) -> str:
        value = _lookup(custom_data, match.group(1))
        if value is None:
            return ""
        if isinstance(value, bool):
            # `str(True)` is "True"; prompt text wants the lowercase JSON form
            # the caller wrote in their own payload.
            return "true" if value else "false"
        return str(value)

    return _PLACEHOLDER.sub(_sub, text)


#: The option fields substitution applies to, per extractor. Absent from this
#: map means "this extractor has no substitutable options", not "substitute
#: everything".
SUBSTITUTABLE_OPTIONS = {
    "kv": ("key_notes", "document_class"),
    "table": ("instructions",),
}

#: The one key inside a `keys` schema whose value is instruction text. A node's
#: NAME is not substitutable (it names an output field), and neither is
#: anything else in the schema -- types, constraints and tolerances are
#: structure, not prose.
_SCHEMA_TEXT_KEY = "description"


def _resolve_schema(node: Any, custom_data: dict[str, Any] | None) -> Any:
    """Substitute in every `description` anywhere in a `keys` schema.

    A recursive walk rather than a shape-aware one on purpose: `kv`'s `keys` is
    a COMPILED schema whose nesting is the compiler's business, and a walk
    keyed on one field name stays correct when that compiler changes. It
    touches nothing else, so a schema with no descriptions is returned
    unchanged (by value -- the input is not mutated).
    """
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == _SCHEMA_TEXT_KEY and isinstance(v, str):
                out[k] = resolve(v, custom_data)
            else:
                out[k] = _resolve_schema(v, custom_data)
        return out
    if isinstance(node, list):
        return [_resolve_schema(v, custom_data) for v in node]
    return node


def resolve_entry(entry: dict[str, Any], custom_data: dict[str, Any] | None) -> dict:
    """Return `entry` with its instruction text substituted.

    Returns a new dict; the caller's validated data is not mutated in place, so
    a failure part-way through cannot leave half-substituted text behind.
    """
    if not entry:
        return entry
    resolved = dict(entry)

    options = resolved.get("options")
    if isinstance(options, dict):
        fields = SUBSTITUTABLE_OPTIONS.get(resolved.get("name"), ())
        if fields:
            options = dict(options)
            for field in fields:
                value = options.get(field)
                if isinstance(value, str) and value:
                    options[field] = resolve(value, custom_data)
            resolved["options"] = options

    if "keys" in resolved:
        resolved["keys"] = _resolve_schema(resolved["keys"], custom_data)
    return resolved


def entry_references(entry: dict[str, Any]) -> list[str]:
    """Every `custom_data` path `entry` references, across all its text.

    Used to answer "does this request use custom_data at all" without
    resolving, which is what lets a submit carrying no placeholders skip the
    walk entirely.
    """
    if not entry:
        return []
    found: dict[str, None] = {}
    options = entry.get("options") or {}
    for field in SUBSTITUTABLE_OPTIONS.get(entry.get("name"), ()):
        value = options.get(field)
        if isinstance(value, str):
            for path in referenced_paths(value):
                found.setdefault(path, None)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == _SCHEMA_TEXT_KEY and isinstance(v, str):
                    for path in referenced_paths(v):
                        found.setdefault(path, None)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(entry.get("keys"))
    return list(found)
