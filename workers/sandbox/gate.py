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
  * Layer 3 — the pod runs non-root on a read-only rootfs with default-deny
    egress and per-job isolation. NOT "with no mounted secrets": an earlier
    version of this line said that, and it is false. `workerPgSandbox`
    attaches the `database` shared-config group, because on the PG transport
    the queue IS Postgres, so the pod necessarily carries
    `DB_HOST/DB_USER/DB_PASSWORD/DB_NAME` and the NetworkPolicy necessarily
    permits db-proxy:5432. See R12 in docs/agent-kv-architecture.md and
    UN-4218.
  * Layer 4/5 — gVisor (deferred) is the syscall-sandbox mitigation that
    turns any in-process escape into a contained one.

So this gate's job is to raise the cost of a bypass — not to be the sole
barrier. Do not treat a pass here as proof the code is safe.

**Measured bypasses (2026-10-04, executed under the production
`python -I -S -E`).** These all return GATE-PASS today, and they are recorded
here so nobody reads the `sys`-handling rationale below as airtight:

  * `statistics.random._os.system('id')` — ran `id`.
  * `collections._sys` *is* the `sys` module.
  * `collections._sys._getframe(0).f_builtins['__imp' + 'ort__']('os')` —
    reaches arbitrary import, because the dunder-subscript check matches only
    *constant* strings and a concatenation is not one.

The root cause is structural: allowlisted modules re-export `sys` and `os` as
NON-dunder attributes (`_sys`, `_os`), and the gate inspects neither. So the
careful `sys`-aliasing rules below are worth materially less than they look —
they close the direct spellings while a one-hop attribute walk through any
allowlisted module goes around them. Closing this properly needs an allowlist
of attribute paths, not a denylist of names; until then the containment
argument rests on layers 2–5, which is what the rest of this module header
says and what the design documents now say too.

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
    "json",
    "math",
    "statistics",
    "decimal",
    "datetime",
    "re",
    "collections",
    "itertools",
    "functools",
    "sys",
}
_DENYLISTED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "breakpoint",
    "input",
    "help",
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


def _rule_import(node, parents) -> str | None:
    """Only allowlisted top-level modules, and `sys` only unaliased."""
    if not isinstance(node, ast.Import):
        return None
    for a in node.names:
        if a.name.split(".")[0] not in _ALLOWED_IMPORTS:
            return f"safety gate: import '{a.name}' is not in the allowed set"
        # `import sys as s` would let aliased sys access dodge the
        # literal-name-"sys" match the bare-Name rule below relies
        # on. Only bare `import sys` is allowed.
        if a.name.split(".")[0] == "sys" and a.asname is not None and a.asname != "sys":
            return "safety gate: 'import sys as ...' is not allowed"
    return None


def _rule_import_from(node, parents) -> str | None:
    """Allowlisted modules only, and no `from sys import ...` in any form."""
    if not isinstance(node, ast.ImportFrom):
        return None
    if (node.module or "").split(".")[0] not in _ALLOWED_IMPORTS:
        return f"safety gate: import '{node.module}' is not in the allowed set"
    # `from sys import argv` (or anything else from sys) binds names
    # directly with no ast.Name(id='sys') reference for the rule
    # below to see. Reject all from-sys forms outright.
    if (node.module or "").split(".")[0] == "sys":
        return "safety gate: 'from sys import ...' is not allowed"
    return None


def _rule_denylisted_call(node, parents) -> str | None:
    """A direct call to a denylisted builtin, e.g. `eval(...)`."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
        return None
    if node.func.id in _DENYLISTED_CALLS:
        return f"safety gate: disallowed call '{node.func.id}'"
    return None


def _rule_dangerous_attribute(node, parents) -> str | None:
    """Reject an attribute REFERENCE to a dangerous name, not only an
    immediate call: `f = b.eval` binds eval under another name, then
    `f(...)` runs it with no attribute left to check -- the old
    call-only check (`b.eval(...)`) missed this. Catching the
    `.eval` access itself closes it, and subsumes the call form
    (a call's `.func` is a Load attribute too). `compile` is
    excluded via _DENYLISTED_ATTR_CALLS so `re.compile(...)` still
    works.
    """
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr in _DENYLISTED_ATTR_CALLS
    ):
        return f"safety gate: disallowed attribute access '{node.attr}'"
    return None


def _rule_dunder_attribute(node, parents) -> str | None:
    """Any dunder attribute access at all."""
    if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
        return f"safety gate: dunder attribute access '{node.attr}'"
    return None


def _rule_builtins_subscript(node, parents) -> str | None:
    """A string subscript like `x['__builtins__']` reaches the builtins
    / globals mapping without any ast.Attribute node for the dunder
    check to see. Reject a constant string slice that is a dunder or
    names the builtins/globals mapping. (py3.12: `node.slice` is the
    expression directly -- no ast.Index wrapper.)
    """
    if not isinstance(node, ast.Subscript):
        return None
    key = node.slice
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        name = key.value
        if name in {"__builtins__", "__globals__"} or (
            name.startswith("__") and name.endswith("__")
        ):
            return f"safety gate: disallowed subscript key '{name}'"
    return None


def _rule_sys_name(node, parents) -> str | None:
    """The name `sys` may be used ONLY as the immediate value of a
    `sys.argv` attribute access. This subsumes a plain denylist of
    dangerous sys attributes (sys.modules, sys._getframe, ...)
    AND closes the aliasing bypass a denylist alone can't: once
    `sys` is bound to another name (`x = sys`, `f = [sys]`,
    `g(sys)`, ...) that name has no attribute-check tying it back
    to `sys`, but the *reference to `sys` itself* right here is
    still caught, no matter what happens to it afterwards.
    """
    if not (
        isinstance(node, ast.Name) and node.id == "sys" and isinstance(node.ctx, ast.Load)
    ):
        return None
    parent = parents.get(node)
    if not (
        isinstance(parent, ast.Attribute)
        and parent.attr == _SYS_ALLOWED_ATTR
        and parent.value is node
    ):
        return "safety gate: 'sys' may only be used as 'sys.argv'"
    return None


def _rule_denylisted_name(node, parents) -> str | None:
    """A bare reference to a denylisted name, whether or not it is called."""
    if isinstance(node, ast.Name) and (
        node.id in _DENYLISTED_NAMES or node.id in _DENYLISTED_CALLS
    ):
        return f"safety gate: disallowed name '{node.id}'"
    return None


# ORDER IS BEHAVIOUR. These were an if/elif chain, so at most one rule ever
# fired per node and the earlier rule owned the message. The loop below returns
# on the first non-None for the same reason -- reordering these changes which
# reason a given input reports.
_RULES = (
    _rule_import,
    _rule_import_from,
    _rule_denylisted_call,
    _rule_dangerous_attribute,
    _rule_dunder_attribute,
    _rule_builtins_subscript,
    _rule_sys_name,
    _rule_denylisted_name,
)


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
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    for node in ast.walk(tree):
        for rule in _RULES:
            reason = rule(node, parents)
            if reason is not None:
                return False, reason
    return True, ""
