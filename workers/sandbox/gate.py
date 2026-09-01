"""Normative AST safety gate for LLM-generated post-processing code.

This is the authoritative copy: the sandbox NEVER trusts the client-side
pre-flight check in the agentic_kv engine (``engine/code_executor._check_code_safe``,
kept there as defense-in-depth). Fail-closed static allowlist — rejects imports outside
the allowed set, dynamic-exec calls, dunder attribute access and introspection-escape
names; permits the name ``sys`` used ONLY as ``sys.argv`` (the runner invokes generated
scripts as ``argv[1]=input path, argv[2]=output path``, so scripts legitimately read
``sys.argv`` — nothing else on ``sys`` is needed, and ``sys`` is the one allowed name
with a dangerous surface: ``sys.modules`` reaches already-imported modules like ``os``
without an ``import os``, ``sys._getframe``/``sys.settrace`` are classic sandbox-escape
primitives, and the bare name itself can be aliased — ``x = sys`` — to reach any of
that through a different name, so any Load reference to ``sys`` other than the
immediate ``sys.argv`` attribute access is rejected, not just a denylist of
attributes) and ``open()`` on the runner's two argv paths.
"""
import ast

_ALLOWED_IMPORTS = {
    "json", "math", "statistics", "decimal", "datetime", "re", "collections",
    "itertools", "functools", "sys",
}
_DENYLISTED_CALLS = {
    "eval", "exec", "compile", "__import__", "globals", "vars",
    "getattr", "setattr", "delattr", "breakpoint", "input", "help",
}
# Attribute-form calls only (e.g. `mod.compile(...)`): `compile` is excluded
# because it's the one denylisted name that collides with a legitimate
# allowlisted-module method, `re.compile`. No allowlisted module exposes any
# of the other denylisted names as safe attributes, so this differs from
# _DENYLISTED_CALLS only by that one entry. The bare-Name branch below still
# rejects a bare `compile(...)` builtin call unconditionally.
_DENYLISTED_ATTR_CALLS = _DENYLISTED_CALLS - {"compile"}
_DENYLISTED_NAMES = {"__builtins__", "__globals__", "__loader__", "__import__"}
# The only sys attribute generated code legitimately needs.
_SYS_ALLOWED_ATTR = "argv"


def check_code_safe(code: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``reason`` is user-safe (no paths)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"safety gate: code does not parse ({e.msg})"
    # ast.walk is flat (no parent access) — build a child->parent map once so
    # the bare-`sys`-Name rule below can tell `sys.argv` (permitted) apart
    # from every other reference to the name `sys` (rejected), including
    # ones with no ast.Attribute node at all, e.g. `x = sys`.
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    return False, f"safety gate: import '{a.name}' is not in the allowed set"
                # `import sys as s` would let aliased sys access dodge the
                # literal-name-"sys" match the bare-Name rule below relies
                # on. Only bare `import sys` is allowed.
                if a.name.split(".")[0] == "sys" and a.asname is not None and a.asname != "sys":
                    return False, "safety gate: 'import sys as ...' is not allowed"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
                return False, f"safety gate: import '{node.module}' is not in the allowed set"
            # `from sys import argv` (or anything else from sys) binds names
            # directly with no ast.Name(id='sys') reference for the rule
            # below to see. Reject all from-sys forms outright.
            if (node.module or "").split(".")[0] == "sys":
                return False, "safety gate: 'from sys import ...' is not allowed"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.id}'"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _DENYLISTED_ATTR_CALLS:
                return False, f"safety gate: disallowed call '{node.func.attr}'"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"safety gate: dunder attribute access '{node.attr}'"
        elif isinstance(node, ast.Name) and node.id == "sys" and isinstance(node.ctx, ast.Load):
            # The name `sys` may be used ONLY as the immediate value of a
            # `sys.argv` attribute access. This subsumes a plain denylist of
            # dangerous sys attributes (sys.modules, sys._getframe, ...)
            # AND closes the aliasing bypass a denylist alone can't: once
            # `sys` is bound to another name (`x = sys`, `f = [sys]`,
            # `g(sys)`, ...) that name has no attribute-check tying it back
            # to `sys`, but the *reference to `sys` itself* right here is
            # still caught, no matter what happens to it afterwards.
            parent = parents.get(node)
            if not (
                isinstance(parent, ast.Attribute)
                and parent.attr == _SYS_ALLOWED_ATTR
                and parent.value is node
            ):
                return False, "safety gate: 'sys' may only be used as 'sys.argv'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_NAMES:
            return False, f"safety gate: disallowed name '{node.id}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_CALLS:
            return False, f"safety gate: disallowed name '{node.id}'"
    return True, ""
