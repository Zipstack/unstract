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
]


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
