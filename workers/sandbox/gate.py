r"""Normative AST safety gate for LLM-generated post-processing code.

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
    egress. NOT "with per-job isolation", and NOT "with no mounted secrets":
    earlier versions of this line said each of those, and both are false.
    There is NO per-job isolation -- R12 below establishes that the sandboxed
    child runs as the SAME UID as the worker process, and `workerPgSandbox`
    runs CONCURRENCY 2 sharing one PID namespace and one `/tmp` emptyDir, so
    co-resident lanes are two jobs of possibly different tenants with no
    boundary between them. Claiming isolation here while citing R12 two lines
    down made this block contradict its own reference. `workerPgSandbox`
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
`test_no_allowlisted_module_still_reaches_a_dangerous_one` walks every
module-valued attribute of every module in `_ALLOWED_IMPORTS` two hops deep,
rather than case by case, so a new allowlist entry that re-exports something
dangerous is caught by the test rather than by inspection. It is NOT a closure
proof, and an earlier version of this paragraph called it one: its `dangerous`
set omits `builtins`, `types`, `codecs`, `marshal`, `gc`, `inspect` and
`operator`, and `json.codecs.builtins` IS the builtins module and is accepted.
Nothing reachable from there executes a code object — an exhaustive depth-3
walk over every permitted attribute edge found only `compile`, `open`,
`json.load(s)` and `itemgetter` — so this is not a bypass. Do not cite the test
as exhaustive.

**What a gate bypass costs, stated plainly.** `runner.py` writes the submitted
code verbatim to `script.py` and runs it as `python -I -S -E script.py`, with
builtins UNRESTRICTED. So a bypass is not a narrow leak, it is arbitrary Python
in the child — `open()` and `eval()` included, and from there
`/proc/<ppid>/environ` is the parent worker's environment. An earlier
description of this PR called the residual "a world-readable file", which
understated it; a reviewer said so on #2309 and was right.

**Four routes were open until 2026-11-09**, each found by a reviewer who re-ran
it, and each re-verified here by EXECUTION before being closed — the frame
snippet returned `eval('1+1') == 2` and a working `open` under the child's own
invocation:

  * `g().gi_frame.f_builtins['eval']` on a generator, and the same via
    `cr_frame`/`ag_frame`/`tb_frame` — no underscore, no dunder, no `sys`, so
    every rule passed it. Now `_rule_introspection_attribute`, keyed on the
    `f_`/`gi_`/`cr_`/`ag_`/`tb_` prefixes rather than a list of today's names.
  * `case object(__builtins__=b)` — a class pattern's keyword attributes live
    in `MatchClass.kwd_attrs` as plain strings, so no `ast.Attribute` node
    exists to match. Now `_rule_match_class_attribute`.
  * `eval = (\n    eval\n)` — the shadowing exemption compared line numbers
    only, so a RHS on a later line than its own target read as already bound.
  * `[(eval := eval)('...') for _ in [0]]` — a walrus in a comprehension binds
    in the ENCLOSING scope (PEP 572), so it was not a comprehension-local.

One further sub-claim in that report did not reproduce, and is recorded here so
nobody re-opens it: `f = eval` was already refused by `_rule_denylisted_name`.

**The `del eval` sub-claim was dismissed too fast, and that was wrong.** This
header previously said it "contains no `ast.Load` at all (at module level it
raises `NameError` before anything could use it)". True of `del eval` ALONE --
and false the moment a binding precedes it, which the reviewer pointed out after
the five routes above were closed:

    eval = 1      # creates the module global the exemption keys on
    del eval      # removes it at runtime
    f = eval      # falls through globals to the REAL builtin

That gate-passed and executed (`f('1+1') == 2`). Closed by
`_module_scope_deleted_names`. The lesson worth keeping is about the shape of
the mistake rather than the route: testing `del eval` on its own answered a
narrower question than the one being asked, and the write-up then recorded the
narrow answer as a general one.

**What is NOT fixed, and must not be read as fixed.** The dunder-subscript check
still matches only *constant* strings, so `d['__imp' + 'ort__']` is still
GATE-PASS on its own (verified 2026-10-23). More importantly the
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
mapping (``x['__builtins__']``); and it restricts the name ``sys`` to an
allowlist of attributes, defined by ``_SYS_ALLOWED_ATTRS`` and enforced by
``_rule_sys_name`` — read those two for what is permitted, rather than a count
restated here. ``sys`` is the one allowed name with a dangerous surface:
``sys.modules`` reaches already-imported modules like ``os`` without an
``import os``, ``sys._getframe``/``sys.settrace`` are classic sandbox-escape
primitives, and the bare name itself can be aliased — ``x = sys`` — to reach
any of that through a different name, so the rule works on the NAME and
permits only an immediate attribute access drawn from that allowlist, rather
than denylisting individual attributes.

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
#: The `sys` attributes generated code legitimately needs.
#:
#: A SET, not one name, and `exit`/`stderr`/`stdout` are here because the
#: codegen prompt steers the model straight at them: it instructs "Include
#: proper error handling", "Use standard library only (json, sys, datetime,
#: re)" and "The script must accept two command line arguments". Error handling
#: in a two-argv script is spelled `sys.exit(1)` or `sys.stderr.write(...)`, and
#: refusing those cost a terminally FAILED job -- after three LLM stages had
#: already been billed, because `executor/tasks.py` flushes `usage_records`
#: before it branches on success -- with an error that reads as a security
#: violation by the caller.
#:
#: This costs nothing in closure. `_rule_sys_name`'s load-bearing property is
#: that a Load of `sys` must be the IMMEDIATE `.value` of a permitted attribute
#: access, so `x = sys`, `g(sys)` and `f = [sys]` still fire however this set
#: grows, `sys.modules`/`sys.settrace` stay refused, and `sys._getframe` is
#: independently refused by `_rule_private_attribute`.
_SYS_ALLOWED_ATTRS = frozenset({"argv", "exit", "stderr", "stdout"})


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
    # THE MEMBER, not just the module. `from X import Y` is semantically `X.Y`,
    # so a member has to face the same checks an attribute access would -- and
    # it was facing none of them, because a from-import binds a fresh local name
    # with no `ast.Attribute` node for `_rule_private_attribute`,
    # `_rule_dangerous_attribute` or `_rule_sys_reexport` to inspect.
    #
    # That was arbitrary code execution, not a hygiene gap. CPython's
    # `collections/__init__.py` does `import sys as _sys`, so
    # `from collections import _sys as s` handed the submitted code the REAL sys
    # module, and `s.modules['posix'].system(...)` followed. Verified by
    # execution before this check existed: `posix.getuid()` ran in the child and
    # returned the worker's uid.
    #
    # Underscore-prefixed members are refused for the same reason
    # `_rule_private_attribute` refuses underscore attributes: a module's
    # privates are where its own imports live, and generated transformation code
    # has no business reading them. `sys` by name and the denylisted attribute
    # set are refused because `from json import codecs` style re-exports reach
    # the same places `_rule_sys_reexport` and `_rule_dangerous_attribute` close
    # on the attribute path.
    for alias in node.names:
        name = alias.name
        if name.startswith("_"):
            return f"safety gate: private from-import member '{name}'"
        if name == "sys":
            return f"safety gate: 'from {node.module} import sys' is not allowed"
        if name in _DENYLISTED_ATTR_CALLS or name in _DENYLISTED_NAMES:
            return f"safety gate: disallowed from-import member '{name}'"
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


#: CPython's introspection attribute prefixes: frame (`f_`), generator
#: (`gi_`), coroutine (`cr_`), async-generator (`ag_`) and traceback (`tb_`)
#: internals. None is underscore-prefixed, so `_rule_private_attribute` never
#: sees them, and none appears in the public API of any module in
#: `_ALLOWED_IMPORTS`.
_INTROSPECTION_ATTR_PREFIXES = ("f_", "gi_", "cr_", "ag_", "tb_")


def _rule_introspection_attribute(node, parents) -> str | None:
    """Frames and friends: the route to the real builtins with no underscore.

    `def g(): yield 1` then `g().gi_frame.f_builtins['eval']` names no dunder,
    no `sys` and no denylisted attribute, so every other rule passed it. This
    was not a reading -- run as the child actually runs
    (`python -I -S -E script.py`) the snippet yielded the REAL `eval`
    (`eval('1+1') == 2`) and the real `open`. `runner.py` writes the submitted
    code verbatim with unrestricted builtins, so that is arbitrary execution,
    and from any frame `f_globals`/`f_builtins` is the whole interpreter.

    The same hole exists on `cr_frame` (coroutine), `ag_frame` (async
    generator) and `tb_frame` (traceback), each reachable without importing
    anything.

    A PREFIX rule, not a list of today's attribute names: `f_back` walks to the
    caller's frame and `gi_code`/`cr_code` hand out a code object, so an
    enumeration would leave the next one open.
    """
    if isinstance(node, ast.Attribute) and node.attr.startswith(
        _INTROSPECTION_ATTR_PREFIXES
    ):
        return f"safety gate: introspection attribute access '{node.attr}'"
    return None


def _rule_match_class_attribute(node, parents) -> str | None:
    """`case object(__builtins__=b)` -- an attribute read with no `ast.Attribute`.

    A class pattern's keyword names live in `MatchClass.kwd_attrs` as plain
    STRINGS, and matching one performs a real `getattr`. Every attribute rule
    above is keyed on an `ast.Attribute` node, so none of them can see this:
    `case object(__builtins__=b)` and `case object(__globals__=g)` both
    gate-passed at the head this rule was added to.

    Checked against the same prefixes and denylist the attribute rules use, so
    the three cannot drift apart.
    """
    if not isinstance(node, ast.MatchClass):
        return None
    for attr in node.kwd_attrs or ():
        if attr.startswith("_"):
            kind = "dunder" if attr.startswith("__") else "private"
            return f"safety gate: {kind} attribute access '{attr}' in a class pattern"
        if attr.startswith(_INTROSPECTION_ATTR_PREFIXES):
            return (
                f"safety gate: introspection attribute access '{attr}' "
                "in a class pattern"
            )
        if attr in _DENYLISTED_ATTR_CALLS:
            return (
                f"safety gate: disallowed attribute access '{attr}' " "in a class pattern"
            )
        if attr == "sys":
            # The FOURTH predicate, missing from this rule's first version --
            # which is why
            # `test_a_class_pattern_refuses_whatever_the_attribute_form_refuses`
            # now exists: four attribute-name predicates live in four separate
            # rules, and re-listing three of them here was the mistake.
            #
            # `import statistics` then `match statistics: case object(sys=s)`
            # bound the REAL `sys` module, and `s.modules['posix'].getuid()`
            # then ran -- verified by execution, it printed the uid.
            # `_rule_sys_reexport` refuses the ordinary `statistics.sys`
            # spelling and cannot see a pattern's keyword strings.
            #
            # Flat refusal with no `sys.argv` carve-out: `_rule_sys_name`
            # permits attributes OF the name `sys`, whereas a pattern keyword
            # named `sys` always reads `.sys` OFF another object, which is the
            # re-export `_rule_sys_reexport` exists to stop.
            return (
                "safety gate: 'sys' reached as an attribute of another module "
                "in a class pattern"
            )
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
    """The name `sys` may be used ONLY as the immediate value of one of
    `_SYS_ALLOWED_ATTRS`. This subsumes a plain denylist of
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
        and parent.attr in _SYS_ALLOWED_ATTRS
        and parent.value is node
    ):
        # Comma-separated, NOT "/" -- `test_hostile_code_rejected` asserts a
        # reason carries no "/" so a filesystem path cannot leak through one.
        return "safety gate: 'sys' may only be used as " + ", ".join(
            f"sys.{a}" for a in sorted(_SYS_ALLOWED_ATTRS)
        )
    return None


#: Scopes in which a bound name is local for the WHOLE scope, so a Load of it
#: can never fall through to builtins -- Python raises UnboundLocalError
#: instead. Order of binding vs. use is therefore irrelevant inside these.
#: The subset of `_FUNCTION_SCOPES` that a walrus does NOT bind into: a
#: `NamedExpr` in a comprehension binds in the ENCLOSING scope (PEP 572).
_COMPREHENSION_SCOPES = (
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)

_FUNCTION_SCOPES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


#: Module-level statements whose execution is UNCONDITIONAL given that control
#: reached them, so a later Load in the same scope is guaranteed to see the
#: binding. Deliberately excludes `If`/`For`/`While`/`Try`/`With`/`Match`:
#: `if False: eval = 1` lexically precedes a Load and never runs, and
#: `for vars in rows:` binds nothing when `rows` is empty -- in both cases the
#: Load still falls through globals to the builtin.
_UNCONDITIONAL_STMTS = (
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
)


def _names_bound_by(stmt) -> list[tuple[str, int]]:
    """Names one statement binds, without descending into nested scopes."""
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [(stmt.name, stmt.lineno)]
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return [(a.asname or a.name.split(".")[0], stmt.lineno) for a in stmt.names]
    out: list[tuple[str, int]] = []
    if isinstance(stmt, ast.AnnAssign) and stmt.value is None:
        # A bare annotation (`eval: int`) binds NOTHING -- the name stays
        # unassigned, so a later Load still falls through to the builtin.
        return []
    if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
        for t in targets:
            for n in ast.walk(t):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    out.append((n.id, n.lineno))
    return out


def _unconditional_module_bindings(module) -> dict[str, tuple[int, ast.stmt]]:
    """Names bound by an unconditional direct statement of the module body.

    Returns the binding's line AND the statement that performs it. The
    statement is not decoration: `_shadows_builtin` has to know whether a Load
    sits INSIDE the binding statement, where the binding has not happened yet.
    """
    # MEMOISED, and that is a correctness-adjacent fact rather than a tidy-up.
    # `_shadows_builtin` calls this once per Load, and the loop below walks the
    # whole module body, so the pair was O(loads x statements): a legal
    # module-scope script reading a shadowed name 4000 times (50.9 KB, well
    # under `SANDBOX_MAX_CODE_BYTES`) took 27.5s to CHECK, on the worker thread,
    # before the child is spawned and so bounded by neither the wall-clock
    # timeout nor `RLIMIT_CPU`. Measured 0.42 / 1.72 / 6.74 / 27.50s at n =
    # 500 / 1000 / 2000 / 4000 -- each doubling quadrupling, which is the shape.
    # Reported as a High on #2309.
    #
    # The cache lives ON the module node, not in a module-level dict or an
    # `lru_cache`: it is then reachable only while this tree is, so it cannot
    # retain one request's parsed tenant code after the check returns. The tree
    # is not mutated between calls within a single `check_code_safe`.
    cached = getattr(module, "_gate_unconditional_bindings", None)
    if cached is not None:
        return cached
    out: dict[str, tuple[int, ast.stmt]] = {}
    for stmt in getattr(module, "body", []):
        if not isinstance(stmt, _UNCONDITIONAL_STMTS):
            continue
        for name, lineno in _names_bound_by(stmt):
            if name not in out or lineno < out[name][0]:
                out[name] = (lineno, stmt)
    module._gate_unconditional_bindings = out
    return out


def _declares_global(scope, name: str) -> bool:
    """Does ``scope`` declare ``name`` ``global`` (or ``nonlocal``) in its own body?

    Module-level, with one definition, because two uses need the same answer:
    `_function_scope_binds` (a declared name is not a local, so the scope
    shadows nothing) and `_target_is_function_local` below (a declared name's
    `for`/`with`/`except` target writes the MODULE binding, so a `del` of it
    unbinds the global). Keeping one copy is deliberate -- re-listing a
    predicate is what left `sys` out of the class-pattern rule earlier in this
    PR.

    Nested scopes are not descended into: a `global` in there is that scope's
    business.
    """
    nested = _FUNCTION_SCOPES + (ast.ClassDef,)

    def walk(n, top=False):
        if not top and isinstance(n, nested):
            return False
        if isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names:
            return True
        return any(walk(c) for c in ast.iter_child_nodes(n))

    return walk(scope, top=True)


def _target_is_function_local(node, parents, name: str) -> bool:
    """Is ``node``'s binder inside a function that treats ``name`` as a LOCAL?

    `_in_function_scope` asked only whether the binder sat lexically inside a
    function, and that is not the same question. With ``global eval`` in scope,
    a `for eval in ...` target writes the MODULE binding, so deleting it in the
    loop body unbinds the global and the next read reaches the real builtin:

        def g():
            global eval
            for eval in [1]:
                del eval
                f = eval      # the real builtin
            return f

    That gate-passed on the commit that introduced the coarse check, and
    calling through `f` sidesteps `_rule_denylisted_call` as well. Reported by
    greptile.
    """
    cur = parents.get(node)
    while cur is not None:
        if isinstance(cur, _FUNCTION_SCOPES):
            return not _declares_global(cur, name)
        if isinstance(cur, ast.Module):
            return False
        cur = parents.get(cur)
    return False


def _module_scope_deleted_names_for(node, parents) -> set[str]:
    """``_module_scope_deleted_names`` for the module ``node`` belongs to."""
    cur = node
    while cur is not None:
        if isinstance(cur, ast.Module):
            return _module_scope_deleted_names(cur)
        cur = parents.get(cur)
    return set()


def _delete_unbinds(target) -> list[str]:
    """Names a single ``del`` TARGET actually unbinds.

    ``del d["k"]`` and ``del obj.attr`` call ``__delitem__`` /
    ``__delattr__`` -- they do NOT unbind ``d`` or ``obj``. Collecting every
    ``ast.Name`` under ``ast.walk(target)`` therefore over-refused ordinary
    calculation code: ``vars = {"drop": 1}; del vars["drop"]; print(vars)``
    came back ``disallowed name 'vars'``, and ``del vars.value`` with it.
    Reported on #2309 alongside the bypasses this rule exists for -- a guard
    that refuses valid work is its own defect, not a safe default.

    Tuple, list and starred targets ARE unbindings, for every name in them.
    """
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_delete_unbinds(element))
        return names
    if isinstance(target, ast.Starred):
        return _delete_unbinds(target.value)
    # Subscript / Attribute: a container or attribute mutation, not an unbind.
    return []


def _global_deletes_in(scope) -> set[str]:
    """Names ``scope`` declares ``global`` AND deletes, at any depth in it.

    Both halves are required. Deleting a plain local is safe (the name stays
    local, so a later read is an ``UnboundLocalError``), and a bare
    ``global eval`` with no ``del`` removes nothing.
    """
    declared: set[str] = set()
    deleted: set[str] = set()

    def walk(n):
        if isinstance(n, ast.Global):
            declared.update(n.names)
        elif isinstance(n, ast.Delete):
            for target in n.targets:
                deleted.update(_delete_unbinds(target))
        for child in ast.iter_child_nodes(n):
            walk(child)

    walk(scope)
    return declared & deleted


def _module_scope_deleted_names(module) -> set[str]:
    """Names a module-scope ``del`` removes, at any depth below the body.

    The shadowing exemption asks whether a Load reads the submitted code's OWN
    local. A ``del`` makes that false again, and the collector above could not
    see it: ``ast.Delete`` is not in ``_UNCONDITIONAL_STMTS``, so only BINDS
    were ever recorded. That left this GATE-PASS and executing --

        eval = 1
        del eval
        f = eval

    -- because the Assign creates the module global ``_shadows_builtin`` keys
    on, the ``del`` removes it at runtime, and the Load then falls through
    globals to the real builtin. Verified by execution: ``f`` IS
    ``builtins.eval`` and ``f('1+1')`` returns 2. Reported by a reviewer on
    #2309 after the first five routes were closed.

    CONSERVATIVE on purpose, in two ways:

    * a ``del`` withdraws the exemption for that name across the WHOLE module,
      not just for Loads after its line. Ordering is not the hard part here;
      reachability is.
    * a ``del`` in a branch counts. ``eval = 1`` then ``if x: del eval`` then
      ``f = eval`` is bound at the read only when the branch did NOT run, and
      the gate cannot know which -- so it refuses. Over-refusal is the safe
      direction, and generated transformation code has no reason to ``del`` a
      builtin's name at all.

    Nested function and class scopes are skipped: a ``del`` in there removes a
    LOCAL of that scope and says nothing about the module global.
    """
    cached = getattr(module, "_gate_deleted_names", None)
    if cached is not None:
        return cached
    nested = _FUNCTION_SCOPES + (ast.ClassDef,)
    found: set[str] = set()

    def walk(n, top=False):
        if not top and isinstance(n, nested):
            # A `del` in here unbinds that scope's LOCAL, which is safe: the
            # name stays local for the whole scope, so a later read raises
            # UnboundLocalError rather than reaching builtins.
            #
            # EXCEPT a name the scope declares `global`. Then the `del` removes
            # the MODULE binding when the function runs, and a module-level read
            # afterwards falls through to the builtin --
            # `eval = 1; def g(): global eval; del eval` then `g(); f = eval`
            # gate-passed and executed until this arm existed.
            found.update(_global_deletes_in(n))
            return
        if isinstance(n, ast.Delete):
            for target in n.targets:
                found.update(_delete_unbinds(target))
        for child in ast.iter_child_nodes(n):
            walk(child)

    walk(module, top=True)
    module._gate_deleted_names = found
    return found


def _is_descendant(node, ancestor, parents) -> bool:
    """Is `node` somewhere inside `ancestor`? Walks the `parents` map upward."""
    cur = parents.get(node)
    while cur is not None:
        if cur is ancestor:
            return True
        cur = parents.get(cur)
    return False


def _function_scope_binds(scope, name: str) -> bool:
    """Does `scope` bind `name` in its own body (not inside a nested scope)?

    Order is irrelevant: Python makes a name bound anywhere in a function local
    for the WHOLE function, so a read before the assignment raises
    UnboundLocalError rather than reaching builtins.
    """
    nested = _FUNCTION_SCOPES + (ast.ClassDef,)

    # `global eval` / `nonlocal eval` removes the name from this scope's local
    # namespace for the WHOLE scope, so the scope binds nothing locally and the
    # Load must fall through to the module rule. This has to be decided BEFORE
    # the walk below, not inside it: the walk's own Global arm returns False for
    # that one node, and the `any(...)` recursion around it then finds the
    # assignment's Store and answers True -- defeating the exemption in exactly
    # the case it exists for, since one writes `global X` in order to assign X.
    # Measured: `def f(): global eval; e = eval; eval = 1` gate-passed and
    # executed `__import__('os').getuid()` through the real builtin, because the
    # module global is unset at the read and falls through to builtins.
    if _declares_global(scope, name):
        return False

    # A walrus inside a COMPREHENSION binds in the enclosing scope, not in the
    # comprehension -- so `[(eval := eval)('...') for _ in [0]]` is not a
    # comprehension-local `eval`, and the RHS Load is the real builtin. The
    # walk below sees the NamedExpr's Store and used to answer True, which
    # gate-passed that snippet. Collect those targets and skip them here; the
    # Load then falls through to the enclosing scope's rule, which refuses it.
    walrus_targets: set[int] = set()
    if isinstance(scope, _COMPREHENSION_SCOPES):
        for n in ast.walk(scope):
            if isinstance(n, ast.NamedExpr):
                for t in ast.walk(n.target):
                    if isinstance(t, ast.Name):
                        walrus_targets.add(id(t))

    def walk(n, top=False):
        if not top and isinstance(n, nested):
            # A nested scope: only its NAME is bound out here.
            return getattr(n, "name", None) == name
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            if n.id == name and id(n) not in walrus_targets:
                return True
        elif isinstance(n, ast.arg) and n.arg == name:
            return True
        elif isinstance(n, ast.ExceptHandler) and n.name == name:
            return True
        elif isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names:
            # `global vars` makes it a MODULE binding, not a local, so it
            # shadows nothing here -- fall through to the module rule.
            return False
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            if any((a.asname or a.name.split(".")[0]) == name for a in n.names):
                return True
        elif isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name == name:
            return True
        elif isinstance(n, ast.MatchMapping) and n.rest == name:
            return True
        return any(walk(c) for c in ast.iter_child_nodes(n))

    return walk(scope, top=True)


def _outer_evaluated(scope) -> set[int]:
    """Sub-trees of `scope` that Python evaluates in the ENCLOSING scope.

    A parameter default is the trap: `lambda eval=eval: eval` looks like a scope
    that binds `eval`, and the default's own Load of `eval` is a child of the
    Lambda node -- but defaults are evaluated at DEFINITION time, outside, where
    `eval` is still the builtin. Verified executing before this check existed:
    `f = (lambda eval=eval: eval)()` then `f("__import__('os').getuid()")`
    returned the worker's uid.

    Annotations, `returns`, decorators, class bases/keywords and a
    comprehension's OUTERMOST iterable are all evaluated outside for the same
    reason.
    """
    regions = []
    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        a = scope.args
        regions += [d for d in a.defaults if d is not None]
        regions += [d for d in (a.kw_defaults or []) if d is not None]
        for grp in (a.posonlyargs, a.args, a.kwonlyargs):
            regions += [x.annotation for x in grp if x.annotation is not None]
        for x in (a.vararg, a.kwarg):
            if x is not None and x.annotation is not None:
                regions.append(x.annotation)
        if getattr(scope, "returns", None) is not None:
            regions.append(scope.returns)
        regions += list(getattr(scope, "decorator_list", []))
    elif isinstance(scope, ast.ClassDef):
        regions += list(scope.bases)
        regions += [k.value for k in scope.keywords]
        regions += list(scope.decorator_list)
    elif isinstance(scope, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        if scope.generators:
            regions.append(scope.generators[0].iter)
    out: set[int] = set()
    for r in regions:
        for n in ast.walk(r):
            out.add(id(n))
    return out


def _in_guarded_body(stmt, child) -> bool:
    """Is `child` one of the statements that only runs AFTER `stmt` binds?

    `for`/`with`/`except` bind their target before their BODY runs -- but not
    before every sub-tree of the statement. `For.iter`,
    `With.items[].context_expr` and `ExceptHandler.type` are all evaluated
    FIRST, while the name still resolves to the builtin, and `For.orelse` can
    run with the target never bound at all (an empty iterable). So the
    exemption covers the body and nothing else.

    This is the statement-level mirror of `_outer_evaluated`, which draws the
    same distinction for parameter defaults, annotations, decorators, class
    bases and a comprehension's outermost iterable. Every region excluded
    there was a measured bypass before it was excluded, and so was every
    region excluded here -- at module scope `for eval in [eval]: e = eval`
    gate-passed and then executed `__import__('os').getuid()` as the worker's
    own uid. Measured across 13 pre-binding regions x 10 denylisted names:
    130/130 refused with this, 0/130 without it.

    `child` is the caller's trailing ancestor -- the direct child of `stmt` on
    the path down to the Load -- so this is an identity scan of a statement
    list, not a traversal. An earlier version collected the body's node ids
    with `ast.walk` on every call, which is correct and quadratic: a legal
    32,916-byte script with 2,000 reads inside one loop took 61.5s to check
    against 0.066s before, occupying a worker lane for a minute before the
    child's timeout even starts. Caching that id set is NOT the alternative --
    an `id()`-keyed cache can collide once a tree is collected, and a stale hit
    exempts a Load that should be refused, which is the one direction this
    layer must not fail in.
    """
    body = getattr(stmt, "body", None)
    if not isinstance(body, list):
        return False
    return any(child is sub for sub in body)


def _binds_as_own_target(stmt, name: str, child) -> bool:
    """Does `stmt` bind `name` as the target guarding the region `child` is in?

    Both halves are load-bearing. `stmt` must bind the name as its own target,
    AND the Load must sit in the body that binding guards -- see
    `_in_guarded_body` for why the rest of the statement is not covered.
    `child` is the caller's trailing ancestor, the direct child of `stmt` on
    the path to the Load.
    """
    if not _in_guarded_body(stmt, child):
        return False
    if isinstance(stmt, (ast.For, ast.AsyncFor)):
        return any(
            isinstance(n, ast.Name) and n.id == name for n in ast.walk(stmt.target)
        )
    if isinstance(stmt, (ast.With, ast.AsyncWith)):
        for item in stmt.items:
            if item.optional_vars is not None and any(
                isinstance(n, ast.Name) and n.id == name
                for n in ast.walk(item.optional_vars)
            ):
                return True
        return False
    if isinstance(stmt, ast.ExceptHandler):
        return stmt.name == name
    return False


def _shadows_builtin(node, parents) -> bool:
    """Is this Load a reference to a LOCAL of that name rather than the builtin?

    A flat "is the name bound anywhere in the module" test got this wrong, and
    wrong here was arbitrary code execution: a parameter named `eval` in one
    function exempted `e = eval` at module level, where it still resolved to the
    real builtin. Two rules, and the difference between them is the point:

    * **A function scope that binds the name** exempts every Load of it in that
      scope, in any order -- the name is local for the whole scope, so a read
      before the assignment raises UnboundLocalError and cannot reach builtins.
      Enclosing function scopes count, for closures.
    * **Module scope** exempts a Load only when an UNCONDITIONAL direct
      statement of the module body binds the name on an earlier line. Lexical
      precedence alone is not enough -- see `_UNCONDITIONAL_STMTS`.

    Where the Load sits in a function and only the module binds the name, this
    refuses: the function may be called before the module-level assignment runs
    and we cannot know. That particular case over-refuses, which is the safe
    direction.

    **It does not follow that the rule as a whole errs that way, and an earlier
    version of this docstring claimed it did.** That sentence was false at six
    sites and was the one a reader would cite to conclude the exemption is safe.
    Being right about where a binding applies is a soundness claim, and each
    region where it was wrong -- parameter defaults, bare annotations, and the
    pre-binding regions `_in_guarded_body` now excludes -- reached a real builtin
    and executed arbitrary code. Both helpers this calls carry the measurement
    rather than a reassurance; read them before widening anything here.
    """
    # `prev` trails `cur` by one, so it is always the direct child of `cur` on
    # the path down to the Load. That is what makes the guarded-region test
    # below an identity check against `cur.body` instead of a walk of it.
    prev = node
    cur = parents.get(node)
    while cur is not None:
        # Does THIS scope actually enclose the Load at runtime? A parameter
        # default, annotation, decorator, class base or outermost comprehension
        # iterable is evaluated in the ENCLOSING scope, so the scope it is
        # written inside does not shadow anything for it.
        if id(node) in _outer_evaluated(cur):
            prev, cur = cur, parents.get(cur)
            continue
        # An ENCLOSING compound statement that binds the name as its own target
        # exempts the Load, at any scope: a `for`/`with`/`except` body only runs
        # after the target is assigned, so inside it the name cannot be the
        # builtin. This is what makes `for input in rows: print(input)` work at
        # module level, where the `for` itself is not an unconditional binding
        # (an empty `rows` binds nothing, so a Load AFTER the loop is refused).
        if _binds_as_own_target(cur, node.id, prev):
            # A module-scope `for`/`with`/`except` target can be unbound by a
            # `del` in its own body -- `for eval in [1]: del eval; f = eval`
            # with the read INSIDE the body gate-passed and executed, because
            # this branch returns before the Module arm below is reached.
            #
            # Scoped to module-scope binders, NOT applied blanket. A first
            # version of this check sat above the whole walk and refused
            # `vars = {}; del vars` followed by `def t(vars): return vars["n"]`
            # -- the parameter is a function LOCAL that no module-level delete
            # can touch, so refusing it broke valid calculations.
            if _target_is_function_local(cur, parents, node.id):
                return True
            if node.id in _module_scope_deleted_names_for(cur, parents):
                return False
            return True
        if isinstance(cur, _FUNCTION_SCOPES):
            if _function_scope_binds(cur, node.id):
                return True
        elif isinstance(cur, ast.Module):
            # A module-scope `del` withdraws the exemption: the binding the
            # collector found may not exist at the read, and the Load then
            # reaches the builtin.
            if node.id in _module_scope_deleted_names(cur):
                return False
            bound = _unconditional_module_bindings(cur).get(node.id)
            if bound is not None:
                pos, stmt = bound
                # `pos < node.lineno` ALONE was unsound. In
                # `eval = (\n    eval\n)` the RHS sits on a later line than
                # the target, so the comparison called it shadowed -- but the
                # binding does not exist until the RHS has been evaluated, so
                # that Load is the real builtin. Measured: gate-passed, and the
                # name bound was `eval` itself. A binding therefore never
                # exempts a Load inside the binding statement.
                if pos < node.lineno and not _is_descendant(node, stmt, parents):
                    return True
        prev, cur = cur, parents.get(cur)
    return False


def _rule_denylisted_name(node, parents) -> str | None:
    """A REFERENCE to a denylisted builtin, whether or not it is called.

    Two conditions. `ast.Load` is what makes this a reference rather than a
    binding -- without it `vars = {}` was refused as a security violation. And
    `_shadows_builtin` is what distinguishes the submitted code's OWN local of
    that name from the builtin: generated code plausibly names a local `input`
    or `vars`, and reading your own local is not a bypass.

    The history is worth keeping, because two cheaper versions of this were
    both wrong. Gating on `ast.Load` alone permitted only the binding, so the
    very next line that read the name was refused again. Exempting any name
    bound ANYWHERE in the module was an exploitable bypass -- Python binds per
    scope, so a parameter named `eval` in one function exempted `e = eval` at
    module level, where it still resolved to the real builtin; `eval = eval`
    did the same, and so did a Store in a dead branch. A static allowlist of
    `{"input"}` was safe but did not cover `vars`, and left `input` as the one
    name where this rule and `_rule_denylisted_call` failed to compose
    (`[input][0]()` called the builtin through a subscript).

    `_shadows_builtin` is scope- and reachability-aware, which is what the
    problem actually requires; see its docstring for the two rules. A direct
    call of a denylisted builtin remains `_rule_denylisted_call`'s, untouched.
    """
    if (
        isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Load)
        and (node.id in _DENYLISTED_NAMES or node.id in _DENYLISTED_CALLS)
        and not _shadows_builtin(node, parents)
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
    _rule_introspection_attribute,
    _rule_match_class_attribute,
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
        # `.msg` only. `str(e)` carries the offending source line and position,
        # which is the generated code -- not something to echo to the caller.
        return False, f"safety gate: code does not parse ({e.msg})"
    except (MemoryError, RecursionError, ValueError) as e:
        # NOT only SyntaxError, and this is the arm that matters. CPython
        # raises MemoryError("Parser stack overflowed - Python source too
        # complex to parse") on a long or deeply-nested source: reachable at
        # roughly 20 KB, which is well UNDER SANDBOX_MAX_CODE_BYTES (65536),
        # so tasks.py's size cap lets it through. Uncaught it propagated out of
        # `check_code_safe` -> `run_code` -> the Celery task, breaking the
        # "always return a structured RunResult" contract that this module and
        # tasks.py both document. RecursionError is the same family, and
        # ValueError is how a NUL byte spells it on CPython <= 3.11.
        #
        # The reason names the exception TYPE, never its text: only
        # SyntaxError.msg is known to be user-safe.
        return False, f"safety gate: code does not parse ({type(e).__name__})"
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
