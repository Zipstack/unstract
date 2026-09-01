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
