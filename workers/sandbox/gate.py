"""Normative AST safety gate for LLM-generated post-processing code.

This is the authoritative copy: the sandbox NEVER trusts the client-side
pre-flight check in the agentic_kv engine (``engine/code_executor._check_code_safe``,
kept there as defense-in-depth). Fail-closed static allowlist — rejects imports outside
the allowed set, dynamic-exec calls, dunder attribute access and introspection-escape
names; permits ``sys`` restricted to ``sys.argv`` only (the runner invokes generated
scripts as ``argv[1]=input path, argv[2]=output path``, so scripts legitimately read
``sys.argv`` — nothing else on ``sys`` is needed, and ``sys`` is the one allowed
module with a dangerous surface: ``sys.modules`` reaches already-imported modules
like ``os`` without an ``import os``, ``sys._getframe``/``sys.settrace`` are classic
sandbox-escape primitives) and ``open()`` on the runner's two argv paths.
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
_DENYLISTED_NAMES = {"__builtins__", "__globals__", "__loader__", "__import__"}
# The only sys attribute generated code legitimately needs.
_SYS_ALLOWED_ATTR = "argv"


def check_code_safe(code: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``reason`` is user-safe (no paths)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"safety gate: code does not parse ({e.msg})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in _ALLOWED_IMPORTS:
                    return False, f"safety gate: import '{a.name}' is not in the allowed set"
                # `import sys as s` would let aliased sys access dodge the
                # sys-attribute check below (which matches on the literal
                # name `sys`). Only bare `import sys` is allowed.
                if a.name.split(".")[0] == "sys" and a.asname is not None and a.asname != "sys":
                    return False, "safety gate: 'import sys as ...' is not allowed"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
                return False, f"safety gate: import '{node.module}' is not in the allowed set"
            # `from sys import argv` (or anything else from sys) binds names
            # directly with no ast.Attribute node for the sys-attribute
            # check below to see — e.g. `from sys import modules` would
            # otherwise dodge it entirely. Reject all from-sys forms.
            if (node.module or "").split(".")[0] == "sys":
                return False, "safety gate: 'from sys import ...' is not allowed"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.id}'"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.attr}'"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"safety gate: dunder attribute access '{node.attr}'"
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "sys"
            and node.attr != _SYS_ALLOWED_ATTR
        ):
            # sys is the one allowed module with a dangerous surface
            # (sys.modules, sys._getframe, sys.settrace, sys.path, ...);
            # restrict it to sys.argv, the only attribute generated code
            # legitimately needs.
            return False, f"safety gate: disallowed sys attribute '{node.attr}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_NAMES:
            return False, f"safety gate: disallowed name '{node.id}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_CALLS:
            return False, f"safety gate: disallowed name '{node.id}'"
    return True, ""
