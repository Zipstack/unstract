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

**The re-export bypasses measured on 2026-10-04 are now REJECTED** (re-run
against this file's rule chain, 2026-10-23). They were GATE-PASS when they were
found; they are recorded here because the rules that close them are not
self-explanatory and must not be deleted as redundant:

  * `statistics.random._os.system('id')` — rejected by `_rule_private_attribute`
    (`private attribute access '_os'`).
  * `collections._sys` — rejected by `_rule_private_attribute`
    (`private attribute access '_sys'`).
  * `collections._sys._getframe(0).f_builtins['__imp' + 'ort__']('os')` —
    rejected by `_rule_private_attribute` as well. The reason it reports
    `_getframe` rather than `_sys` is only `ast.walk` order: both attributes
    match, and either one is enough.
  * The non-underscore spelling of the same walk, `statistics.sys`, is what
    `_rule_sys_reexport` closes (`'sys' reached as an attribute of another
    module`) — `_rule_private_attribute` never sees it, because `sys` has no
    leading underscore.

The three rules are complementary, not duplicates, and none is redundant:
`_rule_private_attribute` covers `_sys`/`_os`-style re-exports,
`_rule_sys_reexport` covers the plain `.sys` attribute, and `_rule_sys_name`
restricts the *name* `sys` to `sys.argv`.
`test_no_allowlisted_module_still_reaches_a_dangerous_one` asserts the closure
exhaustively — it walks every module-valued attribute of every module in
`_ALLOWED_IMPORTS` two hops deep — rather than case by case, so a new allowlist
entry that re-exports something dangerous is caught by the test rather than by
inspection.

**What is NOT fixed, and must not be read as fixed.** The dunder-subscript check
still matches only *constant* strings, so `d['__imp' + 'ort__']` is still
GATE-PASS on its own (verified 2026-10-23) — what changed is that the `_sys`
spelling above no longer gets you a frame to subscript. More importantly the
structural point stands unchanged: this is a denylist of names over a dynamic
language, the closure above is a closure of the paths that exist in *today's*
stdlib, and the worst case in the threat model needs no import at all (see
`open()` below). Closing this class properly needs an allowlist of attribute
paths, not a denylist of names; until then the containment argument rests on
layers 2–5, which is what the rest of this module header says and what the
design documents say too.

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
rejected, not just a denylist of attributes).

**``open()`` is NOT restricted, and this gate attempts no path or argument check
of any kind.** An earlier version of this docstring said ``open()`` was permitted
only "on the runner's two argv paths". That was never implemented: the nine-rule
chain in ``_RULES`` inspects imports, call/attribute/name identifiers and
*constant* subscript keys, and **no rule relates a call's arguments to its
callee** — argument expressions are walked like any other node, so a dangerous
*spelling* inside one is still caught, but nothing constrains which VALUE may be
passed to a given function. ``open`` is in neither ``_DENYLISTED_CALLS`` nor
``_DENYLISTED_NAMES``, so ``open('/etc/passwd')``, ``open('../../secret.txt')``
and ``open('/tmp/evil', 'w')`` all GATE-PASS (verified 2026-10-23), exactly like
the legitimate ``open(sys.argv[1])``.

Path restriction is deliberately **not attempted here**, and adding it is the
repo owner's call, not a drive-by. Two reasons:

  1. Generated code legitimately needs ``open()`` (it reads ``argv[1]`` and
     writes ``argv[2]``), so the control would have to be an *argument* allowlist
     — and a static AST check over a dynamic language cannot carry one. The path
     reaching ``open`` need not be a literal: ``open(p)``, ``open(base + name)``,
     a dict lookup, or a name bound three statements earlier all defeat a
     constant-argument check while reading as safe. That buys the appearance of
     containment, which is worse than the honest absence of it, because the
     appearance is what gets cited in a review.
  2. The exposure that matters does not depend on which path is opened.
     ``open('/proc/<ppid>/environ')`` returns the parent's full *unscrubbed*
     environment — including ``DB_PASSWORD`` — because ``runner.py`` spawns the
     child with no ``user=``/``group=`` and it inherits the consumer's UID. No
     import is needed, so neither ``_ALLOWED_IMPORTS`` nor any rule below bounds
     it. A path check here would be read as closing that, and it would not.

The containment for that is layers 2–5 plus the narrowly-scoped queue/result DB
role tracked as **UN-4218**; see accepted residual **R12** in
``docs/agent-kv-architecture.md``, which says this layer "should be read as
best-effort hygiene, not containment".
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


def _rule_private_attribute(node, parents) -> str | None:
    """Any underscore-prefixed attribute access, dunder or single.

    Widened from dunders only, because single-underscore attributes are how an
    allowlisted module hands out one that is not: `statistics.random._os` and
    `collections._sys` both resolve to the real modules on 3.12, and `_os` is
    not a dunder, so the old rule passed them. The module allowlist is only
    layer 1 and layers 2-5 still contain what they reach, but the accepted
    residual was written as "`os` is outside the allowlist, so there is no path
    to a secret, a cross-tenant read, or exfiltration" -- which these made
    false. Generated transformation code has no business reading a module's
    privates, so the whole prefix goes.
    """
    if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
        kind = "dunder" if node.attr.startswith("__") else "private"
        return f"safety gate: {kind} attribute access '{node.attr}'"
    return None


def _rule_sys_reexport(node, parents) -> str | None:
    """`anything.sys` -- the re-export that walks around the `sys.argv` rule.

    `_rule_sys_name` restricts the NAME `sys` to `sys.argv` and closes aliasing
    (`import sys as s`, `from sys import ...`). It cannot see `statistics.sys`,
    which is the same module reached as an attribute of an allowlisted one, and
    from there `sys.modules['os']` is the whole interpreter. Blocking the
    attribute name closes that without touching the permitted `sys.argv`, which
    is an attribute access ON the name `sys`, not an attribute NAMED `sys`.
    """
    if isinstance(node, ast.Attribute) and node.attr == "sys":
        return "safety gate: 'sys' reached as an attribute of another module"
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
    _rule_private_attribute,
    _rule_sys_reexport,
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
