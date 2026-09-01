"""Normative AST safety gate for LLM-generated post-processing code.

This is the authoritative copy: the sandbox NEVER trusts the client-side
pre-flight check in the agentic_kv engine (``engine/code_executor._check_code_safe``,
kept there as defense-in-depth). Fail-closed static allowlist — rejects imports outside
the allowed set, dynamic-exec calls, dunder attribute access and introspection-escape
names; permits ``open()`` on the runner's two argv paths.
"""
import ast

_ALLOWED_IMPORTS = {"json", "math", "statistics", "decimal", "datetime", "re", "collections", "itertools", "functools"}
_DENYLISTED_CALLS = {
    "eval", "exec", "compile", "__import__", "globals", "vars",
    "getattr", "setattr", "delattr", "breakpoint", "input", "help",
}
_DENYLISTED_NAMES = {"__builtins__", "__globals__", "__loader__", "__import__"}


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
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
                return False, f"safety gate: import '{node.module}' is not in the allowed set"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.id}'"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.attr}'"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"safety gate: dunder attribute access '{node.attr}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_NAMES:
            return False, f"safety gate: disallowed name '{node.id}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_CALLS:
            return False, f"safety gate: disallowed name '{node.id}'"
    return True, ""
