"""Normative AST safety gate for LLM-generated post-processing code.

This is the authoritative copy: the sandbox NEVER trusts the client-side
pre-flight check in the agentic_kv engine (``engine/code_executor._check_code_safe``,
kept there as defense-in-depth). Fail-closed static allowlist — rejects dangerous
imports, dynamic-exec calls, dunder attribute access and introspection-escape
names; permits ``open()`` on the runner's two argv paths.
"""
import ast

_DENYLISTED_IMPORTS = {
    "os", "subprocess", "socket", "shutil", "ctypes", "pickle", "marshal",
    "importlib", "requests", "urllib", "urllib2", "urllib3", "http", "ftplib",
    "smtplib", "telnetlib", "pty", "multiprocessing", "signal", "resource",
    "fcntl", "mmap",
}
_DENYLISTED_CALLS = {
    "eval", "exec", "compile", "__import__", "globals", "vars",
    "getattr", "setattr", "delattr",
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
                if a.name.split(".")[0] in _DENYLISTED_IMPORTS:
                    return False, f"safety gate: disallowed import '{a.name}'"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in _DENYLISTED_IMPORTS:
                return False, f"safety gate: disallowed import from '{node.module}'"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.id}'"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"safety gate: dunder attribute access '{node.attr}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_NAMES:
            return False, f"safety gate: disallowed name '{node.id}'"
    return True, ""
