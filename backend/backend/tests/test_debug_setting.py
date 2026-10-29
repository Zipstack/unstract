"""DEBUG is off unless DJANGO_DEBUG turns it on.

The published backend image runs ``backend.settings.dev`` by default, so a
hardcoded ``DEBUG = True`` there or in ``base.py`` reaches every self-hosted
deployment: unhandled exceptions return Django's technical 500 page (stack
trace, local variables, settings) to the client. Settings are read once at
import, so each case loads them in a fresh interpreter.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[2]
_PROBE = "import importlib, sys; print(importlib.import_module(sys.argv[1]).DEBUG)"


def _debug_for(module: str, **env: str) -> bool:
    base = {k: v for k, v in os.environ.items() if k != "DJANGO_DEBUG"}
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, module],
        cwd=_BACKEND_DIR,
        env={**base, **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    return result.stdout.strip().splitlines()[-1] == "True"


@pytest.mark.parametrize("module", ["backend.settings.base", "backend.settings.dev"])
def test_debug_is_off_when_unset(module: str) -> None:
    assert _debug_for(module) is False


@pytest.mark.parametrize("module", ["backend.settings.base", "backend.settings.dev"])
def test_debug_turns_on_only_when_asked(module: str) -> None:
    assert _debug_for(module, DJANGO_DEBUG="True") is True
    assert _debug_for(module, DJANGO_DEBUG="False") is False
