import pytest

from sandbox.gate import check_code_safe

_SAFE = "import json\nrows=[{'x':1}]\nwith open('out','w') as f:\n    f.write('{}')\n"

_HOSTILE = [
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
        "rec = json.load(open(sys.argv[1]))[\"records\"][0]\n"
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
    for name in ("eval", "exec", "__import__", "globals", "vars", "getattr",
                 "setattr", "delattr", "breakpoint", "input", "help"):
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
        "        record = json.load(f)[\"records\"][0]\n"
        "    record[\"net\"] = round(float(record.get(\"total\", 0)) * 0.9, 2)\n"
        "    with open(sys.argv[2], \"w\") as f:\n"
        "        f.write(json.dumps(record) + \"\\n\")\n"
        "main()\n"
    )
    assert ok is True, reason
    assert reason == ""
