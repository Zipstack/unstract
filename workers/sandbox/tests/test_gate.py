import pytest
from sandbox.gate import check_code_safe

_SAFE = "import json\nrows=[{'x':1}]\nwith open('out','w') as f:\n    f.write('{}')\n"

_HOSTILE = [
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


class TestBareNameExemptionIsNarrow:
    """`_SAFE_AS_BARE_NAME` is the whole exemption, and these pin both halves.

    This class replaces one that tested a flat module-wide "is this name bound
    anywhere" exemption. That exemption was an exploitable bypass: Python binds
    per SCOPE and the set was also order-blind, so a binding that did not
    shadow the builtin at the point of a Load exempted it anyway, and
    `_rule_denylisted_call` only catches a DIRECT call, so an alias walked
    past. Every shape in `test_the_alias_bypass_shapes_are_all_refused` below
    was ACCEPTED by that version and reached real `eval`/`exec`/`__import__`.

    The old class's own guard asserted the opposite and passed throughout,
    because it pinned `g = globals` where `globals` is bound nowhere -- the one
    spelling the defect did not touch. That is why the shapes below are
    enumerated rather than represented by one example.
    """

    def test_a_local_named_input_may_be_read_after_it_is_bound(self):
        # The motivating case, and the only one the exemption covers: the
        # codegen contract is "read the input path from sys.argv[1]", so
        # generated code names a local `input` plausibly often.
        ok, reason = check_code_safe(
            "import json\n"
            "import sys\n"
            "input = json.load(open(sys.argv[1]))\n"
            'rows = input["records"]\n'
        )
        assert ok is True, reason

    def test_a_for_target_named_input_may_be_read_in_the_body(self):
        ok, reason = check_code_safe("rows = [1]\nfor input in rows:\n    print(input)\n")
        assert ok is True, reason

    def test_a_local_named_vars_is_still_refused_deliberately(self):
        # `vars` is NOT exempt, and this is the trade rather than an oversight:
        # `d = vars; d()["__buil" + "tins__"]` reaches `__builtins__` and then
        # `__import__` with no import at all, and the concatenation evades
        # `_rule_builtins_subscript`, which matches only an `ast.Constant`.
        # Generated code that wants that identifier has to pick another one.
        ok, reason = check_code_safe('vars = {}\nvars["a"] = 1\n')
        assert ok is False
        assert reason == "safety gate: disallowed name 'vars'"

    @pytest.mark.parametrize(
        "label,code",
        [
            # Each of these was accepted by the flat-set exemption. The first
            # four are the distinct mechanisms; the rest are the same four
            # reached through other binding forms.
            (
                "cross-scope local",
                "def f():\n    eval = 1\n    return eval\n\ne = eval\nx = e('1')\n",
            ),
            ("alias precedes rebind", "e = eval\nx = e('1')\neval = 1\n"),
            ("store in a dead branch", "if False:\n    eval = 1\ne = eval\nx = e('1')\n"),
            # `eval = eval` resolves the RHS through globals to the BUILTIN, so
            # "rebinding the name itself" did not make later Loads safe either.
            ("self-rebind to the builtin", "eval = eval\nrun = eval\nx = run('1')\n"),
            ("global declaration", "def f():\n    global eval\n\ne = eval\nx = e('1')\n"),
            ("parameter name", "def f(eval):\n    return eval\n\ne = eval\nx = e('1')\n"),
            ("lambda parameter", "f = lambda vars: 0\nx = vars\n"),
            ("comprehension target", "ys = [0 for getattr in []]\ng = getattr\n"),
            (
                "except-as target",
                "try:\n    pass\nexcept Exception as eval:\n    pass\ne = eval\n",
            ),
            ("import alias", "run = __import__\nrun('os')\n__import__ = 1\n"),
        ],
    )
    def test_the_alias_bypass_shapes_are_all_refused(self, label, code):
        ok, reason = check_code_safe(code)
        assert ok is False, f"{label} passed the gate: {code!r}"
        assert reason.startswith("safety gate: disallowed name "), reason

    def test_a_direct_call_of_a_denylisted_builtin_is_still_refused(self):
        # `_rule_denylisted_call`'s own job, pinned here so a later widening of
        # `_SAFE_AS_BARE_NAME` cannot quietly take the call rule with it.
        ok, reason = check_code_safe('eval("1+1")\n')
        assert ok is False
        assert reason == "safety gate: disallowed call 'eval'"

    def test_input_is_still_refused_as_a_call(self):
        # The exemption is on the REFERENCE only. `input` stays in
        # `_DENYLISTED_CALLS`, so the call form is unaffected.
        ok, reason = check_code_safe("x = input()\n")
        assert ok is False
        assert reason == "safety gate: disallowed call 'input'"


class TestEveryRuleIsRegistered:
    """Structural backstop for the `_RULES` tuple `check_code_safe` iterates.

    A rule function that is defined but absent from the tuple is never
    consulted, so the gate silently ACCEPTS what it used to reject. Today that
    cannot slip through unnoticed: dropping any one of the nine rules fails
    between 4 and 17 of this module's cases.

    **Two of every count are this class's own two tests**, which fail for a
    structural reason -- the rule is no longer in `_RULES` -- and not because
    they are hostile cases. So the behavioural kill count per rule is each
    figure minus 2, and the FLOOR of the range is set by that pair rather than
    by any rule's own coverage. An earlier wording attributed the whole of
    each count to "hostile cases of its own", which overstated every rule's
    behavioural coverage by two.

    **Method, because the figures below are a measurement and not an
    estimate**: write a pytest plugin that does
    `gate._RULES = tuple(r for r in gate._RULES if r.__name__ != "<rule>")`,
    run this module under it, and read the `N failed, M passed` summary;
    repeat once per rule. At the commit that added this paragraph that gives
    **77 cases** and per-rule failures **7, 7, 6, 4, 6, 4, 5, 9, 17** in
    `_RULES` order. The measurement spans the WHOLE module, not only the
    classes above this one -- which is how `_rule_sys_reexport` scores 4 when
    nothing above here exercises an attribute named `sys`: its cases live in
    `TestModuleReexportEscapes`, below.

    **Re-derive rather than trust the numbers.** They move with every case
    added to this module, and this paragraph has already been wrong three
    times for that reason: "eight rules / between 3 and 10" (predating
    `_rule_sys_reexport`); "61 cases / the behavioural tests above" (the
    per-rule figures were right, the denominator and the scope were not); and
    "67 cases / 7,7,5,4,6,4,5,9,7", correct when written and stale one commit
    later once `TestBareNameExemptionIsNarrow` replaced its predecessor. Treat
    the method as the durable part and the figures as a dated snapshot. These two tests are here
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
