"""Normative AST safety gate for LLM-generated post-processing code.

LAYER-1 CONTROL ONLY — BEST-EFFORT, NOT A COMPLETE SANDBOX. This is a
fail-closed static AST check that rejects the well-known Python
code-execution and introspection-escape primitives before generated code is
ever run. It is deliberately a denylist-shaped, defense-in-depth control, NOT
a provably airtight allowlist: a determined attacker may still discover a
construction that reaches code execution through it. That residual risk is
contained by the OTHER layers, which are the real security boundary:

  * Layer 2 — the runner scrubs the environment and applies rlimits before
    exec'ing the generated script.
  * Layer 3 — the pod runs non-root on a read-only rootfs with no mounted
    secrets, default-deny egress, and per-job isolation.
  * Layer 4/5 — gVisor (deferred) is the syscall-sandbox mitigation that
    turns any in-process escape into a contained one.

So this gate's job is to CLOSE the cheap, demonstrated bypasses and raise the
cost of the rest — not to be the sole barrier. Do not treat a pass here as
proof the code is safe.

This is also the authoritative copy: the sandbox NEVER trusts the client-side
pre-flight check in the agentic_kv engine (``engine/code_executor._check_code_safe``,
kept there as defense-in-depth). It rejects imports outside the allowed set,
dynamic-exec calls, dunder attribute access, introspection-escape names, an
attribute REFERENCE (not only a call) to a dangerous builtin (``f = b.eval``),
and a string subscript naming a dunder / ``__builtins__`` / ``__globals__``
mapping (``x['__builtins__']``); it permits the name ``sys`` used ONLY as
``sys.argv`` (the runner invokes generated scripts as ``argv[1]=input path,
argv[2]=output path``, so scripts legitimately read ``sys.argv`` — nothing
else on ``sys`` is needed, and ``sys`` is the one allowed name with a
dangerous surface: ``sys.modules`` reaches already-imported modules like
``os`` without an ``import os``, ``sys._getframe``/``sys.settrace`` are classic
sandbox-escape primitives, and the bare name itself can be aliased —
``x = sys`` — to reach any of that through a different name, so any Load
reference to ``sys`` other than the immediate ``sys.argv`` attribute access is
rejected, not just a denylist of attributes) and ``open()`` on the runner's
two argv paths.
"""
import ast

_ALLOWED_IMPORTS = {
    "json", "math", "statistics", "decimal", "datetime", "re", "collections",
    "itertools", "functools", "sys",
}
_DENYLISTED_CALLS = {
    "eval", "exec", "compile", "__import__", "globals", "locals", "vars",
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
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr in _DENYLISTED_ATTR_CALLS
        ):
            # Reject an attribute REFERENCE to a dangerous name, not only an
            # immediate call: `f = b.eval` binds eval under another name, then
            # `f(...)` runs it with no attribute left to check -- the old
            # call-only check (`b.eval(...)`) missed this. Catching the
            # `.eval` access itself closes it, and subsumes the call form
            # (a call's `.func` is a Load attribute too). `compile` is
            # excluded via _DENYLISTED_ATTR_CALLS so `re.compile(...)` still
            # works.
            return False, f"safety gate: disallowed attribute access '{node.attr}'"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"safety gate: dunder attribute access '{node.attr}'"
        elif isinstance(node, ast.Subscript):
            # A string subscript like `x['__builtins__']` reaches the builtins
            # / globals mapping without any ast.Attribute node for the dunder
            # check to see. Reject a constant string slice that is a dunder or
            # names the builtins/globals mapping. (py3.12: `node.slice` is the
            # expression directly -- no ast.Index wrapper.)
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                name = key.value
                if name in {"__builtins__", "__globals__"} or (
                    name.startswith("__") and name.endswith("__")
                ):
                    return False, f"safety gate: disallowed subscript key '{name}'"
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
