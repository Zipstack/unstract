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
            # ---- The PRE-BINDING region of each target-binding statement. ----
            # The entries above cover each compound statement's BODY (accepted,
            # correctly) and its AFTER side (refused, correctly). This is the
            # third region, and it is the one that was missing: `for`/`with`/
            # `except` bind their target before the BODY runs, not before the
            # whole statement, and `For.orelse` can run with the target never
            # bound at all. Every entry below gate-passed and then EXECUTED
            # `__import__('os').getuid()` as the worker's uid before
            # `_guarded_body` existed.
            (
                "for target, read in the ITERABLE",
                "for eval in [eval]:\n    e = eval\nx = e('1')\n",
            ),
            (
                "for target, __import__ through the iterable",
                "for __import__ in [__import__]:\n    f = __import__\nf('os')\n",
            ),
            (
                "for target, iterable via a subscript call",
                "for eval in [[eval][0]('1')]:\n    pass\n",
            ),
            (
                "for target, read in the ELSE clause",
                "for eval in []:\n    pass\nelse:\n    e = eval\n    x = e('1')\n",
            ),
            (
                "with target, read in the CONTEXT EXPR",
                "def mk(v):\n    return open\nwith mk(eval) as eval:\n    pass\n",
            ),
            (
                "except target, read in the EXCEPTION TYPE",
                "def cap(v):\n    return ValueError\n"
                "try:\n    pass\nexcept (ValueError, cap(eval)) as eval:\n    pass\n",
            ),
            # The `global declaration` entry above binds nothing anywhere, so it
            # is refused for a different reason than the one its comment gives.
            # THIS is the shape the `global` arm was written for, and the one
            # that defeated it: you declare `global X` in order to assign X, and
            # the assignment's Store answered the walk before the Global arm
            # could. The module global is unset at the read, so it fell through
            # to builtins.
            (
                "global declaration WITH an assignment",
                "def f():\n"
                "    global eval\n"
                "    e = eval\n"
                "    eval = 1\n"
                "    return e\n"
                "x = f()('1')\n",
            ),
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
            "_rule_introspection_attribute",
            "_rule_match_class_attribute",
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


def test_checking_a_large_script_stays_roughly_linear():
    """The shadowing exemption must not make gate checking quadratic.

    The first version of `_in_guarded_body` collected the enclosing statement
    body's node ids with `ast.walk` on EVERY denylisted-name read, which is
    correct and quadratic in the body size. Measured on the script below
    (32,916 bytes, 2,000 reads of `vars` inside one loop): 61.5s, against 0.066s
    before the exemption existed and 0.094s after it was reworked to an
    identity check against the trailing ancestor.

    This runs in the worker BEFORE the child's timeout starts, so no cap bounds
    it -- a legal script simply occupies a lane. `SANDBOX_MAX_CODE_BYTES`
    defaults to 65536, twice this fixture, so the shape is well inside what a
    caller may submit.

    This is a wall-clock assertion, which this suite otherwise avoids. The
    bound is deliberately ~50x the observed time and ~1/8th of the regression
    it guards, so it discriminates the algorithmic change it is about without
    being sensitive to machine speed. Asserting on a visit count instead would
    need instrumentation inside the rule chain, which is a worse trade than one
    wide bound.
    """
    import time

    body = "\n".join(f"    a{i} = vars" for i in range(2000))
    code = "vars = {}\nfor row in [1]:\n" + body + "\n"
    assert len(code.encode()) < 65536, "fixture must stay a submittable size"

    start = time.perf_counter()
    ok, reason = check_code_safe(code)
    elapsed = time.perf_counter() - start

    # The script is legal: `vars` is a local bound at module scope before use.
    assert ok is True, reason
    assert elapsed < 5.0, (
        f"gate check took {elapsed:.2f}s for a {len(code.encode())}-byte "
        "script; the shadowing exemption has gone quadratic again"
    )


def test_checking_a_large_module_scope_script_stays_roughly_linear():
    """The MODULE-scope path, which the sibling above does not cover.

    That one wraps its reads in a `for` body, so the exemption resolves through
    `_binds_as_own_target`. A shadowed read at module scope instead goes to
    `_unconditional_module_bindings`, which walked the entire module body once
    per Load -- O(loads x statements). The cost is paid on the WORKER thread
    inside `check_code_safe`, before any child exists, so neither the
    wall-clock timeout nor `RLIMIT_CPU` bounds it, and 50.9 KB is under
    `SANDBOX_MAX_CODE_BYTES` (65536) so the size cap does not either.

    **This asserts SCALING, not elapsed time, and the first version of it was
    wrong for exactly that reason.** It asserted `elapsed < 5.0` against a
    locally measured 0.22s -- a 20x margin that looked ample and was not: CI
    runs this suite under `pytest-xdist`, where every worker competes for the
    same runner, and the same check took **8.76s** there. A 40x machine
    difference makes any absolute bound either useless locally or flaky in CI.

    A ratio over a 4x size span does not have that problem: both halves run
    back to back on the same machine, so the machine's speed cancels. Measured
    at n=500 -> n=2000, min of two runs each:

        quadratic (before the memoisation):  ~16.0x   (0.42s -> 6.74s)
        current:                              ~7.0x   (0.01s -> 0.07s)

    The threshold sits between them with room on both sides. Per-doubling
    ratios were ~2.9x current against ~4.0x quadratic, which is too narrow a
    gap to hold up under noise -- hence the wider span.
    """
    import time

    def best_of(n, repeats=2):
        body = "\n".join(f"a{i} = vars" for i in range(n))
        code = "vars = {}\n" + body + "\n"
        assert len(code.encode()) < 65536, "fixture must stay a submittable size"
        times = []
        for _ in range(repeats):
            start = time.perf_counter()
            ok, reason = check_code_safe(code)
            times.append(time.perf_counter() - start)
            assert ok is True, reason
        return min(times)

    small = best_of(500)
    large = best_of(2000)  # 4x the statements

    # Guard against a degenerate denominator on a very fast machine: a clock
    # granularity artefact would otherwise produce a huge ratio and a false
    # failure. 1ms is far below the ~10ms this takes even post-fix.
    assert small > 0.001, f"small case too fast to time reliably ({small:.6f}s)"

    ratio = large / small
    assert ratio < 11.0, (
        f"gate checking scaled {ratio:.1f}x for a 4x larger module-scope script "
        f"({small:.4f}s -> {large:.4f}s); quadratic is ~16x and the current "
        "implementation is ~7x, so the module-binding lookup has likely gone "
        "quadratic again"
    )


class TestDeleteWithdrawsTheShadowingExemption:
    """`del` makes a shadowed name reach the builtin again.

    Reported on #2309 AFTER the five routes in the class below were closed, and
    it is the route I had already dismissed: I tested `del eval` on its own,
    found no `ast.Load`, and recorded "at module level it raises NameError" as
    though that settled the general case. It settles only the narrow one. With a
    binding in front of it the `del` succeeds, and the later Load falls through
    globals to the real builtin -- verified by execution, `f('1+1')` returned 2.
    """

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "bind, del, then read",
                "eval = 1\ndel eval\nf = eval\n",
            ),
            (
                "and call what the read produced",
                "eval = 1\ndel eval\nf = eval\nf('1+1')\n",
            ),
            (
                "del in a branch that may not run",
                "eval = 1\nif 1:\n    del eval\nf = eval\n",
            ),
            (
                "del inside a loop body",
                "eval = 1\nfor _ in [0]:\n    del eval\nf = eval\n",
            ),
            (
                "del via a tuple target",
                "eval = 1\nvars = 2\ndel eval, vars\nf = eval\n",
            ),
            (
                "read BEFORE the del is refused too (reachability, not order)",
                "eval = 1\nf = eval\ndel eval\n",
            ),
        ],
    )
    def test_a_module_scope_del_refuses_the_read(self, label, code):
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label}: gate accepted a read of the real builtin"
        assert reason == "safety gate: disallowed name 'eval'", reason

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "for target, read INSIDE the body",
                "for eval in [1]:\n    del eval\n    f = eval\n",
            ),
            (
                "for target, and call what it produced",
                "for eval in [1]:\n    del eval\n    f = eval\n    f('1+1')\n",
            ),
            (
                "with target, read inside the body",
                "import json\nclass C:\n    def __enter__(self):\n        return 1\n"
                "    def __exit__(self, *a):\n        return False\n"
                "with C() as eval:\n    del eval\n    f = eval\n",
            ),
            (
                "except handler target",
                "try:\n    pass\nexcept Exception as eval:\n    del eval\n    f = eval\n",
            ),
            (
                "global del inside a function the module then calls",
                "eval = 1\ndef g():\n    global eval\n    del eval\ng()\nf = eval\n",
            ),
        ],
    )
    def test_the_check_precedes_every_other_exemption_path(self, label, code):
        """The first fix put the deletion check in the Module arm only.

        A `for`/`with`/`except` target grants its own exemption through
        `_binds_as_own_target`, which returns BEFORE the Module arm is reached
        -- so all four target forms still gate-passed and executed. The
        `global` case is the mirror image: the del is inside a function, which
        the collector skipped, but `global` makes it remove the MODULE binding.
        Both reported by greptile on the commit that closed the first route.
        """
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label}: gate accepted a read of the real builtin"
        assert reason == "safety gate: disallowed name 'eval'", reason

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "del of a dict ENTRY is not an unbind of the dict",
                "vars = {'drop': 1, 'keep': 2}\ndel vars['drop']\nprint(vars)\n",
            ),
            (
                "del of an ATTRIBUTE is not an unbind of the object",
                "import json\nvars = json\ndel vars.dumps\n",
            ),
            (
                "a del of a plain local stays local (UnboundLocalError, not builtins)",
                "def f():\n    eval = 1\n    del eval\n    return eval\n",
            ),
        ],
    )
    def test_it_refuses_only_real_unbindings(self, label, code):
        """The first fix collected every `ast.Name` under the del target, so
        `del vars['drop']` read as deleting `vars` and refused ordinary
        calculation code. A guard that refuses valid work is its own defect.

        The function-local case is here because it is genuinely safe and must
        stay allowed: after `del`, the name is still local for the whole scope,
        so the read raises `UnboundLocalError` rather than reaching builtins.
        """
        ok, reason = check_code_safe(code)
        assert ok is True, f"{label}: gate refused valid code -- {reason}"

    @pytest.mark.parametrize(
        "label,code,refused",
        [
            (
                "a function PARAMETER of the deleted name is a local",
                "vars = {}\ndel vars\ndef transform(vars):\n    return vars['n'] * 2\n",
                False,
            ),
            (
                "a function-scope for target is a local too",
                "def f():\n    for eval in [1]:\n        del eval\n        g = eval\n    return 1\n",
                False,
            ),
            (
                # The case `_in_function_scope` actually exists for, and the
                # one the sibling above does NOT reach: here the `del` is at
                # MODULE scope, so the deleted-names set does contain `vars`,
                # while the Load resolves through a FUNCTION-scope `for`
                # target. Without that guard the module delete would refuse a
                # loop variable it cannot touch. Found by a surviving mutant --
                # removing the guard broke no test until this case existed.
                "a module del must not reach a function's own for target",
                "vars = {}\ndel vars\ndef f(rows):\n    for vars in rows:\n        return vars\n",
                False,
            ),
            (
                "but a function that does NOT bind it still reads the builtin",
                "eval = 1\ndel eval\ndef f():\n    return eval\n",
                True,
            ),
        ],
    )
    def test_a_module_del_does_not_reach_function_locals(self, label, code, refused):
        """Scope, not blanket -- and the first version of this got it wrong.

        The deletion check was hoisted above the whole walk so it could precede
        `_binds_as_own_target`. That also put it ahead of the FUNCTION-scope
        exemptions, and refused `vars = {}; del vars` followed by
        `def transform(vars): ...` -- the parameter is a local that no
        module-level delete can touch, so valid calculations failed without
        running. Reported by greptile on the commit that hoisted it.

        The third case is why the fix is scoping rather than removal: a
        function that does NOT bind the name resolves it through module
        globals at CALL time, so after a module-level `del` it reaches the
        builtin and must still be refused.
        """
        ok, reason = check_code_safe(code)
        assert ok is (not refused), f"{label}: got {'PASS' if ok else reason}"
        if refused:
            assert reason == "safety gate: disallowed name 'eval'", reason

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "a genuine rebinding with no del still shadows",
                "eval = 1\nx = eval\n",
            ),
            (
                "deleting an ordinary name is none of this rule's business",
                "d = {'a': 1}\ndel d\n",
            ),
            (
                "a del in a FUNCTION scope removes a local, not the global",
                "eval = 1\ndef f():\n    eval = 2\n    del eval\nx = eval\n",
            ),
            (
                "del eval alone: no Load at all, and NameError at runtime",
                "del eval\n",
            ),
        ],
    )
    def test_it_does_not_over_refuse(self, label, code):
        """The rule is deliberately conservative, so these are the shapes that
        would show it going too far. The function-scope case is the one that
        matters: a `del` in there is about that scope's local, and treating it
        as a module-scope delete would refuse ordinary code.
        """
        ok, reason = check_code_safe(code)
        assert ok is True, f"{label}: gate refused legitimate code -- {reason}"


class TestFrameAndMatchRoutesToBuiltins:
    """The four routes that gate-passed before `_rule_introspection_attribute`
    and `_rule_match_class_attribute` existed.

    Each was verified by EXECUTION, not by reading: run the way the child runs
    it (`python -I -S -E script.py`), the frame snippet below produced the real
    `eval` -- `eval('1+1')` returned 2 -- and the real `open`. `runner.py`
    writes submitted code verbatim and does not restrict builtins, so a gate
    bypass is arbitrary execution in the child, which is why these are not
    stylistic cases.

    Reported on PR #2309 by a reviewer who re-ran each one. Two further
    sub-claims in that report did NOT reproduce and deliberately have no test
    here: `f = eval` is already refused by `_rule_denylisted_name`, and
    `del eval` contains no `ast.Load` at all (it raises `NameError` at module
    level before anything can use it).
    """

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "generator frame -> f_builtins",
                "def g():\n    yield 1\nb = g().gi_frame.f_builtins['eval']\n",
            ),
            (
                "generator frame -> f_globals",
                "def g():\n    yield 1\nb = g().gi_frame.f_globals\n",
            ),
            (
                "f_back walks to the caller's frame",
                "def g():\n    yield 1\nb = g().gi_frame.f_back\n",
            ),
            (
                "gi_code hands out a code object",
                "def g():\n    yield 1\nc = g().gi_code\n",
            ),
            (
                "coroutine frame",
                "async def c():\n    pass\nf = c().cr_frame\n",
            ),
            (
                "async generator frame",
                "async def a():\n    yield 1\nf = a().ag_frame\n",
            ),
            (
                "traceback frame",
                "import sys\ntb = sys.exc_info()[2]\nf = tb.tb_frame\n",
            ),
        ],
    )
    def test_introspection_attributes_are_refused(self, label, code):
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label}: gate accepted a route to the real builtins"
        assert "introspection attribute" in reason, reason

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "__builtins__ via a class pattern",
                "match 1:\n    case object(__builtins__=b):\n        pass\n",
            ),
            (
                "__globals__ via a class pattern",
                "def f():\n    pass\nmatch f:\n    case object(__globals__=g):\n        pass\n",
            ),
            (
                "a frame attribute via a class pattern",
                "match 1:\n    case object(gi_frame=f):\n        pass\n",
            ),
        ],
    )
    def test_class_pattern_keywords_are_refused(self, label, code):
        """`MatchClass.kwd_attrs` holds plain strings, so no `ast.Attribute`
        node exists for the attribute rules to match -- which is exactly how
        these passed.
        """
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label}: gate accepted an attribute read in a pattern"
        assert "in a class pattern" in reason, reason

    @pytest.mark.parametrize(
        "attr",
        [
            "sys",
            "eval",
            "exec",
            "__builtins__",
            "__globals__",
            "__import__",
            "gi_frame",
            "f_builtins",
            "cr_frame",
            "ag_frame",
            "tb_frame",
            "_sys",
            "_os",
            "_getframe",
            # Names that must stay ALLOWED in both forms, so the test is an
            # equivalence check and not a one-sided "refuse everything".
            "compile",
            "items",
            "fromisoformat",
            "format",
        ],
    )
    def test_a_class_pattern_refuses_whatever_the_attribute_form_refuses(self, attr):
        """The drift guard, and the reason it exists is a real miss.

        Four separate rules key on an attribute NAME -- `_DENYLISTED_ATTR_CALLS`,
        the underscore prefix, the introspection prefixes, and `== "sys"`. The
        first version of `_rule_match_class_attribute` re-listed three of them
        and omitted `sys`, so `import statistics` plus
        `match statistics: case object(sys=s)` bound the real `sys` module and
        `s.modules['posix'].getuid()` ran. Reported by a reviewer on the commit
        that added the rule.

        Re-listing is the hazard, so this asserts the IMPLICATION rather than a
        list of reasons: whatever the ordinary `obj.<attr>` form refuses, the
        pattern form must refuse too. A fifth predicate added to the attribute
        rules and forgotten here fails this test without anyone remembering to
        update it. The converse is deliberately not asserted -- the pattern form
        may be stricter.
        """
        attribute_ok, _ = check_code_safe(f"def f(obj):\n    return obj.{attr}\n")
        pattern_ok, _ = check_code_safe(
            f"match 1:\n    case object({attr}=v):\n        pass\n"
        )
        if not attribute_ok:
            assert not pattern_ok, (
                f"`obj.{attr}` is refused but `case object({attr}=v)` is not: "
                "the class-pattern rule has drifted from the attribute rules"
            )

    @pytest.mark.parametrize(
        "label,code",
        [
            (
                "the binding's own RHS on a later line",
                "eval = (\n    eval\n)\n",
            ),
            (
                "walrus in a comprehension binds OUTSIDE it",
                "[(eval := eval)('1') for _ in [0]]\n",
            ),
        ],
    )
    def test_a_binding_does_not_exempt_its_own_right_hand_side(self, label, code):
        """The shadowing exemption asks whether a Load is the submitted code's
        OWN local. Inside the binding construct it is not: the binding has not
        happened yet, so the Load still resolves to the builtin.
        """
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label}: gate accepted a read of the real builtin"
        assert reason == "safety gate: disallowed name 'eval'", reason

    @pytest.mark.parametrize(
        "label,code",
        [
            ("a genuine rebinding, then a read", "eval = 1\nx = eval\n"),
            ("a local named input", "def f(input):\n    return input\n"),
            ("ordinary attribute work", "import json\nx = json.dumps({'a': 1})\n"),
            (
                "an attribute that merely starts with f",
                "x = 'a,b'.format()\n",
            ),
            (
                "a date helper, not a frame attribute",
                "import datetime\nd = datetime.date.fromisoformat('2026-01-01')\n",
            ),
        ],
    )
    def test_the_new_rules_do_not_over_refuse(self, label, code):
        """The two new rules are prefix- and pattern-keyed, so the risk they
        carry is false refusal of ordinary generated code. These are the shapes
        that would show it.
        """
        ok, reason = check_code_safe(code)
        assert ok is True, f"{label}: gate refused legitimate code -- {reason}"
