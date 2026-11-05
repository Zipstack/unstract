import pytest
from sandbox.gate import check_code_safe

_SAFE = "import json\nrows=[{'x':1}]\nwith open('out','w') as f:\n    f.write('{}')\n"

_HOSTILE = [
    # From-import members bypassed every attribute rule, because a
    # from-import binds a fresh local name with no `ast.Attribute` node to
    # inspect. CPython's `collections/__init__.py` does `import sys as _sys`,
    # so this handed the submitted code the REAL sys module and
    # `s.modules['posix'].system(...)` followed. Verified by execution:
    # `posix.getuid()` ran in the child and returned the worker's uid.
    # Reported by a review bot, not by the lens fan-out -- whose
    # "exhaustive" attribute walk had the same blind spot the gate did.
    "from collections import _sys as s\ns.modules['posix'].system('id')\n",
    "from collections import _sys\nx = _sys.modules\n",
    "from statistics import sys\nx = sys.modules\n",
    "from statistics import _sum\n",
    # Self-shadowing: `eval = eval` rebinds the name to the BUILTIN (the RHS
    # falls through to builtins at module scope), so a "has this name been
    # bound?" exemption lets every later Load through while it still refers
    # to the real builtin. Reached without a call on a Name, so
    # `_rule_denylisted_call` is no backstop. Executed end-to-end past a
    # flat-set exemption and returned the host uid.
    "eval = eval\nfs = [eval]\nfs[0]('1')\n",
    "exec = exec\nd = {'e': exec}\nd['e']('x=1')\n",
    "__import__ = __import__\nfs = [__import__]\nfs[0]('os')\n",
    "import os\nos.system('id')",
    "import subprocess",
    "from socket import socket",
    "import ctypes",
    "eval('1+1')",
    "exec('x=1')",
    "__import__('os')",
    "x = ().__class__.__bases__",
    "b = __builtins__",
    "getattr(object, 'x')",
    "not valid python (",
    "import builtins\nbuiltins.exec('x=1')",
    "from builtins import exec as e\ne('x=1')",
    "import builtins\nx = builtins.eval\nx('1')",
    "import sys\nsys.modules['os'].system('id')",
    "from sys import modules\nmodules['os'].system('id')",
    "import sys\nm = sys.modules",
    "import sys\nsys._getframe(0).f_globals",
    "import sys\nsys.settrace(None)",
    "import sys as s\ns.argv",
    "from sys import argv",
    "import sys\nx = sys\nx.modules",
    "import sys\ny = sys\ny.modules['posix'].system('id')",
    "import sys\nf = [sys]\nf[0].modules",
    "import sys\ndef g(a):\n return a\ng(sys).modules",
    "import posix\nposix.system('id')",
    "from os import path",
    "e = eval\ne('1')",
    "e = exec\ne('x=1')",
    "import functools\nf = functools.partial(eval, '1')\nf()",
    "breakpoint()",
    # locals() is globals() at module scope, so it hands back __builtins__.
    "x = locals()",
    "b = locals()['__builtins__']",
    # Attribute REFERENCE (not an immediate call) that rebinds a dangerous
    # builtin under another name, then calls it.
    "b = {}\nf = b.eval\nf('1')",
    # String-subscript reach for the builtins/globals mapping, invisible to
    # the dunder-attribute check.
    "y = {}\nz = y['__builtins__']",
    "d = {}\ng = d['__globals__']",
]


# The full verified PoC chain from the pre-Greptile review: locals() at module
# scope IS globals(), so ['__builtins__'] hands back the real builtins mapping,
# .eval rebinds eval under another name, and the final call executes. Every
# link is independently rejected now; assert the whole chain is refused.
_POC_CHAIN = (
    "b = locals()['__builtins__']\n"
    "f = b.eval\n"
    "f(\"__import__('os').system('id')\")\n"
)


def test_full_poc_chain_rejected():
    ok, reason = check_code_safe(_POC_CHAIN)
    assert ok is False
    assert reason.startswith("safety gate:")


def test_locals_call_rejected():
    ok, reason = check_code_safe("x = locals()")
    assert ok is False
    assert reason.startswith("safety gate:")


def test_attribute_reference_to_dangerous_name_rejected():
    # `f = b.eval` is an attribute REFERENCE, not an immediate call -- the
    # old gate only rejected `b.eval(...)`.
    ok, reason = check_code_safe("b = {}\nf = b.eval")
    assert ok is False
    assert reason.startswith("safety gate:")


def test_string_subscript_of_dunder_rejected():
    ok, reason = check_code_safe("y = {}\nz = y['__builtins__']")
    assert ok is False
    assert reason.startswith("safety gate:")


def test_sys_argv_int_subscript_still_allowed():
    # sys.argv[1]/[2] are int subscripts -- the dunder-string subscript rule
    # must not touch them, nor json.load(f)["records"][0] (string key that is
    # not a dunder).
    ok, reason = check_code_safe(
        "import json, sys\n"
        'rec = json.load(open(sys.argv[1]))["records"][0]\n'
        "open(sys.argv[2], 'w').write(json.dumps(rec))\n"
    )
    assert ok is True, reason
    assert reason == ""


def test_safe_code_passes():
    ok, reason = check_code_safe(_SAFE)
    assert ok is True, reason
    assert reason == ""


@pytest.mark.parametrize("code", _HOSTILE)
def test_hostile_code_rejected(code):
    ok, reason = check_code_safe(code)
    assert ok is False
    assert reason.startswith("safety gate:")
    # Reason is user-safe: no filesystem paths leak.
    assert "/" not in reason.replace("safety gate:", "")


def test_encoded_import_via_builtins_subscript_rejected():
    ok, _ = check_code_safe("__builtins__['__import__']('os')")
    assert ok is False


def test_allowed_modules_pass():
    ok, reason = check_code_safe("import math\nimport datetime\nx = math.sqrt(4)")
    assert ok is True, reason
    assert reason == ""


def test_realistic_calc_with_safe_builtins_passes():
    ok, reason = check_code_safe(
        "import json\nvals=[1,2,3]\ntotal=sum(vals)\nm=max(vals)\n"
        "with open('o','w') as f:\n    f.write(json.dumps({'t': total, 'm': m}))"
    )
    assert ok is True, reason
    assert reason == ""


def test_sys_argv_allowed_for_runner_contract():
    # The runner invokes generated scripts as `python script.py <in> <out>`;
    # scripts legitimately read/write via sys.argv[1]/sys.argv[2]. `sys` was
    # added to the allowed-imports set for exactly this — see gate.py.
    ok, reason = check_code_safe(
        "import json, sys\n"
        "data = json.load(open(sys.argv[1]))\n"
        "with open(sys.argv[2], 'w') as f:\n"
        "    f.write(json.dumps(data) + '\\n')\n"
    )
    assert ok is True, reason
    assert reason == ""


def test_re_compile_attribute_form_allowed():
    # re is an allowlisted module; `.compile` collides with the denylisted
    # bare-name `compile` builtin but the attribute-form call must still be
    # permitted — see gate.py's _DENYLISTED_ATTR_CALLS.
    ok, reason = check_code_safe("import re\nre.compile('x')")
    assert ok is True, reason
    assert reason == ""


def test_bare_compile_builtin_still_rejected():
    # Only the attribute form (`re.compile`) is exempted; the bare `compile`
    # builtin call must remain blocked.
    ok, reason = check_code_safe("compile('x', '<s>', 'eval')")
    assert ok is False
    assert reason == "safety gate: disallowed call 'compile'"


def test_re_compile_result_used_normally():
    ok, reason = check_code_safe("import re\nx = re.compile('a')\nx.match('a')")
    assert ok is True, reason
    assert reason == ""


def test_eval_attribute_form_still_rejected():
    # `builtins` is not itself an allowlisted module, so this is rejected at
    # the import check before the attribute-form Call check is ever reached
    # — still `ok is False`, which is what matters for the corpus.
    ok, reason = check_code_safe("import builtins\nbuiltins.eval('1')")
    assert ok is False


def test_exec_attribute_form_still_rejected():
    ok, reason = check_code_safe("import builtins\nbuiltins.exec('x=1')")
    assert ok is False


def test_denylisted_attr_calls_excludes_only_compile():
    # Direct check of the fix's structural intent (gate.py's
    # _DENYLISTED_ATTR_CALLS): every other denylisted name — no allowlisted
    # module exposes any of them as a safe attribute — stays denied in the
    # attribute-form branch; only `compile` is exempted, and only there.
    from sandbox.gate import _DENYLISTED_ATTR_CALLS, _DENYLISTED_CALLS

    assert _DENYLISTED_CALLS - _DENYLISTED_ATTR_CALLS == {"compile"}
    assert "compile" in _DENYLISTED_CALLS  # bare-Name branch still has it
    for name in (
        "eval",
        "exec",
        "__import__",
        "globals",
        "vars",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "input",
        "help",
    ):
        assert name in _DENYLISTED_ATTR_CALLS


def test_eval_exec_bare_forms_still_rejected():
    ok, reason = check_code_safe("eval('1+1')")
    assert ok is False
    assert reason == "safety gate: disallowed call 'eval'"
    ok, reason = check_code_safe("exec('x=1')")
    assert ok is False
    assert reason == "safety gate: disallowed call 'exec'"


def test_codegen_template_passes():
    # The real codegen contract: sys used only for sys.argv, json for I/O.
    ok, reason = check_code_safe(
        "import json\n"
        "import sys\n"
        "def main():\n"
        "    with open(sys.argv[1]) as f:\n"
        '        record = json.load(f)["records"][0]\n'
        '    record["net"] = round(float(record.get("total", 0)) * 0.9, 2)\n'
        '    with open(sys.argv[2], "w") as f:\n'
        '        f.write(json.dumps(record) + "\\n")\n'
        "main()\n"
    )
    assert ok is True, reason
    assert reason == ""


class TestShadowedBuiltinsAreScopeResolved:
    """A local that shadows a denylisted builtin is readable; an alias is not.

    `vars` is accepted now, by decision: real codegen names a local `vars`, and
    refusing it gave ordinary generated code a security-flavoured error. What
    makes that safe is that the exemption is scope- AND reachability-aware
    rather than a name allowlist, so it distinguishes the two cases the simpler
    versions could not:

      vars = {}; vars["a"] = 1        <- the code's own local, accepted
      d = vars; d()["__buil"+"tins__"] <- the real builtin, refused

    That second shape is why a flat `{"input", "vars"}` allowlist was rejected:
    it reaches `__builtins__` then `__import__` with no import at all, and the
    concatenation evades `_rule_builtins_subscript`, which matches only an
    `ast.Constant`.

    `test_the_alias_bypass_shapes_are_all_refused` is the load-bearing half.
    Every shape in it was ACCEPTED by at least one earlier implementation, and
    four of them reached real `eval`/`exec`/`__import__` under execution.
    """

    @pytest.mark.parametrize(
        "label,code",
        [
            ("module-level local", "vars = {}\nvars['a'] = 1\n"),
            (
                "local in a function",
                "def f():\n    vars = {}\n    vars['a'] = 1\n    return vars\n",
            ),
            # Local for the WHOLE function, so order does not matter: a read
            # before the assignment raises UnboundLocalError, never the builtin.
            (
                "read before assign, same function",
                "def f():\n    x = vars\n    vars = {}\n    return x\n",
            ),
            (
                "input shadowed at module scope",
                "import json\nimport sys\ninput = json.load(open(sys.argv[1]))\nr = input['records']\n",
            ),
            (
                "input shadowed in a function",
                "import json\nimport sys\ndef f():\n    input = json.load(open(sys.argv[1]))\n    return input['records']\n",
            ),
            # The body only runs once the target is assigned, so a Load inside
            # it cannot be the builtin even though the `for` itself binds
            # nothing when the iterable is empty.
            (
                "for target, read inside the body",
                "rows = [1]\nfor input in rows:\n    print(input)\n",
            ),
            (
                "with ... as, read inside the body",
                "with open('f') as vars:\n    x = vars.read()\n",
            ),
            (
                "except ... as, read inside the body",
                "try:\n    pass\nexcept Exception as input:\n    print(input)\n",
            ),
            (
                "compile as a local",
                "import re\ndef f():\n    compile = re.compile('x')\n    return compile.findall('x')\n",
            ),
            (
                "match capture in a function",
                "def f(m):\n    match m:\n        case [input]:\n            return input\n",
            ),
            ("annotation WITH a value binds", "vars: dict = {}\nvars['a'] = 1\n"),
            (
                "an ordinary default is unaffected",
                "def f(x=1):\n    vars = {}\n    return vars\n",
            ),
        ],
    )
    def test_a_shadowing_local_may_be_read(self, label, code):
        ok, reason = check_code_safe(code)
        assert ok is True, f"{label}: {reason}"

    @pytest.mark.parametrize(
        "label,code",
        [
            # Cross-scope: a function-local binding does not shadow the name at
            # module level, where it still resolves to the builtin.
            (
                "cross-scope local",
                "def f():\n    eval = 1\n    return eval\n\ne = eval\nx = e('1')\n",
            ),
            ("parameter name", "def f(eval):\n    return eval\n\ne = eval\nx = e('1')\n"),
            ("lambda parameter", "f = lambda vars: 0\nx = vars\n"),
            ("comprehension target", "ys = [0 for getattr in []]\ng = getattr\n"),
            # Order: a module-level Load before the assignment falls through
            # globals to builtins.
            ("alias precedes rebind", "e = eval\nx = e('1')\neval = 1\n"),
            (
                "module binds after a function reads it",
                "def f():\n    return vars\nvars = {}\n",
            ),
            # Reachability: these bindings lexically precede and never execute.
            ("store in a dead branch", "if False:\n    eval = 1\ne = eval\nx = e('1')\n"),
            (
                "for target, read AFTER the loop",
                "rows = []\nfor vars in rows:\n    pass\nd = vars\nx = d()\n",
            ),
            (
                "try-body binding",
                "try:\n    vars = {}\nexcept Exception:\n    pass\nd = vars\nx = d()\n",
            ),
            (
                "except target, read AFTER the handler",
                "try:\n    pass\nexcept Exception as eval:\n    pass\ne = eval\nx = e('1')\n",
            ),
            # `global` makes it a MODULE binding, so it shadows nothing locally.
            ("global declaration", "def f():\n    global eval\n\ne = eval\nx = e('1')\n"),
            # Self-rebinding resolves the RHS through globals TO the builtin.
            ("self-rebind to the builtin", "eval = eval\nrun = eval\nx = run('1')\n"),
            ("import alias", "run = __import__\nrun('os')\n__import__ = 1\n"),
            ("nothing bound at all", "d = vars\nx = d()\n"),
            (
                "the builtins chain this exists to stop",
                "d = vars\nb = d()['__buil' + 'tins__']\n",
            ),
            # Evaluated in the ENCLOSING scope, so the scope they are written
            # inside shadows nothing for them. The lambda-default form was
            # verified EXECUTING `__import__('os').getuid()` before this was
            # handled -- reported by a review bot against the very commit that
            # introduced scope resolution.
            ("lambda parameter default", "f = (lambda eval=eval: eval)()\nx = f('1')\n"),
            ("def parameter default", "def g(eval=eval):\n    return eval\nf = g()\n"),
            ("keyword-only default", "def g(*, eval=eval):\n    return eval\n"),
            ("parameter annotation", "def g(x: eval):\n    pass\n"),
            ("return annotation", "def g() -> eval:\n    pass\n"),
            (
                "decorator expression",
                "def d(fn):\n    return fn\n\n@d\ndef g(eval=eval):\n    return eval\n",
            ),
            ("class base", "class C(eval):\n    pass\n"),
            ("outermost comprehension iterable", "ys = [0 for eval in (eval,)]\n"),
            # A bare annotation binds NOTHING; the name stays unassigned.
            ("annotation without a value", "eval: int\nf = eval\nx = f('1')\n"),
        ],
    )
    def test_the_alias_bypass_shapes_are_all_refused(self, label, code):
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label} passed the gate: {code!r}"
        assert reason.startswith("safety gate: disallowed name "), reason

    def test_a_direct_call_of_a_denylisted_builtin_is_still_refused(self):
        # `_rule_denylisted_call`'s own job, pinned here so a later widening of
        # the shadowing logic cannot quietly take the call rule with it.
        ok, reason = check_code_safe('eval("1+1")\n')
        assert ok is False
        assert reason == "safety gate: disallowed call 'eval'"

    def test_calling_a_shadowed_name_is_still_refused(self):
        # The shadowing exemption is on the REFERENCE. A local that shadows a
        # denylisted builtin and is then CALLED still trips the call rule --
        # a false refusal for a caller who shadowed a callable, and the safe
        # direction for a rule that cannot see what the local holds.
        ok, reason = check_code_safe("def f():\n    vars = dict\n    return vars()\n")
        assert ok is False
        assert reason == "safety gate: disallowed call 'vars'"


class TestEveryRuleIsRegistered:
    """Structural backstop for the `_RULES` tuple `check_code_safe` iterates.

    A rule function that is defined but absent from the tuple is never
    consulted, so the gate silently ACCEPTS what it used to reject. Today that
    cannot slip through unnoticed: dropping any one of the nine rules fails
    several of this module's cases, because each existing rule has hostile cases
    of its own -- plus this class's own two tests, which fail structurally for
    any single-rule removal.

    **No figures here, deliberately.** A denominator and a per-rule kill list
    lived in this paragraph and were wrong four times running: "eight rules /
    between 3 and 10" (predating `_rule_sys_reexport`), "61 cases / the
    behavioural tests above" (right counts, wrong denominator and scope), "67 /
    7,7,5,4,6,4,5,9,7" (correct when written, stale one commit later), and "77 /
    ...,17" (short by the three `_HOSTILE` entries the same commit added). The
    figures move with every case added to this module, so a snapshot here is a
    claim that goes stale faster than anyone re-derives it.

    **The method is the durable part, so re-derive rather than trust a number:**
    write a pytest plugin that does
    `gate._RULES = tuple(r for r in gate._RULES if r.__name__ != "<rule>")`, run
    this module under it, and read the `N failed, M passed` summary; repeat once
    per rule. The measurement spans the whole module, not only the classes above
    this one -- which is how `_rule_sys_reexport` scores at all when nothing
    above here exercises an attribute named `sys`: its cases are in
    `TestModuleReexportEscapes`, below. These two tests are here
    for the rules that do not exist yet -- a new rule added without a
    registry entry, or added with cases that overlap an earlier rule's -- where
    the behavioural tests would pass while the rule did nothing.
    """

    def test_every_rule_function_is_registered(self):
        from sandbox import gate

        defined = {
            name
            for name, obj in vars(gate).items()
            if name.startswith("_rule_") and callable(obj)
        }
        registered = {rule.__name__ for rule in gate._RULES}
        assert defined == registered, (
            "these rule functions are defined but never consulted: "
            f"{sorted(defined - registered)}"
        )

    def test_the_registry_order_is_the_documented_one(self):
        """Order is behaviour: the first matching rule owns the reason string."""
        from sandbox import gate

        assert [rule.__name__ for rule in gate._RULES] == [
            "_rule_import",
            "_rule_import_from",
            "_rule_denylisted_call",
            "_rule_dangerous_attribute",
            "_rule_private_attribute",
            "_rule_sys_reexport",
            "_rule_builtins_subscript",
            "_rule_sys_name",
            "_rule_denylisted_name",
        ]


class TestModuleReexportEscapes:
    """An allowlisted module handing out one that is not.

    All three were ACCEPTED before (verified on 3.12.9) and all three reach the
    real `os`: `statistics.random._os` and `collections._sys` directly, and
    `statistics.sys` because the `sys.argv` restriction only constrains the NAME
    `sys`, not an attribute NAMED `sys` on something else. `sys.modules['os']`
    is then the whole interpreter.

    The gate is layer 1 of five and was never the boundary, so these were not
    an escape from the sandbox -- layers 2-5 still deny egress, scrub the env
    and hold no secret beyond the pod's own transport. What they did break is
    the accepted residual as written: "`pathlib`, `os`, `socket` and `urllib`
    are all outside the allowlist, so there is no path to a secret, a
    cross-tenant read, or exfiltration."
    """

    def test_private_module_attribute_reaches_os(self):
        ok, reason = check_code_safe(
            "import statistics\nstatistics.random._os.listdir('/')"
        )
        assert ok is False
        assert "_os" in reason

    def test_private_sys_alias_reaches_os(self):
        ok, reason = check_code_safe(
            "import collections\ncollections._sys.modules['os'].listdir('/')"
        )
        assert ok is False
        assert "_sys" in reason

    def test_sys_as_an_attribute_walks_around_the_argv_restriction(self):
        """The one the `sys.argv` rule could not see, by construction."""
        ok, reason = check_code_safe(
            "import statistics\nstatistics.sys.modules['os'].listdir('/')"
        )
        assert ok is False
        assert "sys" in reason

    def test_sys_argv_itself_still_works(self):
        """The restriction permits exactly this, and must keep permitting it --
        the generated code's only way to find its input and output paths.
        """
        ok, reason = check_code_safe(
            "import json\nimport sys\n"
            "with open(sys.argv[1]) as f:\n    d = json.load(f)\n"
            "with open(sys.argv[2], 'w') as f:\n    f.write('{}')\n"
        )
        assert ok is True, reason

    def test_no_allowlisted_module_still_reaches_a_dangerous_one(self):
        """Exhaustive rather than a list of the three that were reported: walk
        every module-valued attribute of every allowlisted module and assert the
        gate refuses any two-hop path to a dangerous module or to sys.modules.
        """
        import importlib
        import types

        from sandbox.gate import _ALLOWED_IMPORTS

        dangerous = {
            "os",
            "subprocess",
            "socket",
            "shutil",
            "ctypes",
            "pickle",
            "importlib",
            "urllib",
            "http",
        }
        accepted = []
        for name in sorted(_ALLOWED_IMPORTS):
            try:
                mod = importlib.import_module(name)
            except Exception:  # pragma: no cover - allowlist is importable
                continue
            for first in dir(mod):
                if first.startswith("__"):
                    continue
                hop = getattr(mod, first, None)
                if not isinstance(hop, types.ModuleType):
                    continue
                for second in dir(hop):
                    if second.startswith("__"):
                        continue
                    target = getattr(hop, second, None)
                    reaches = (
                        isinstance(target, types.ModuleType)
                        and target.__name__.split(".")[0] in dangerous
                    ) or second == "modules"
                    if not reaches:
                        continue
                    expr = f"{name}.{first}.{second}"
                    ok, _ = check_code_safe(f"import {name}\n{expr}")
                    if ok:
                        accepted.append(expr)
        assert not accepted, f"the gate still accepts: {sorted(accepted)}"


def test_a_from_import_of_an_allowlisted_module_is_permitted():
    """`_rule_import_from`'s accept path was the one uncovered line in the
    module: every from-import in the corpus is hostile, so a regression
    rejecting ALL from-imports would reject legitimate generated code with
    nothing to catch it. Not a security hole -- a job failure, which is why
    this is the cheap positive case rather than another hostile one.
    """
    ok, reason = check_code_safe("from json import dumps\nx = dumps({})\n")
    assert ok is True, reason
