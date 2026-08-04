"""``ConcurrencyMode`` must stay a ``StrEnum`` (UN-3893).

``StateStore`` guards every set/get/clear with ``cls.mode == ConcurrencyMode.THREAD``
and raises ``RuntimeError("Unknown concurrency mode")`` otherwise. With a bare
``Enum`` that guard had two runtime failure modes, both invisible until production:

1. ``mode`` is read as ``os.environ.get("CONCURRENCY_MODE", ConcurrencyMode.THREAD)``,
   so SETTING the variable yields a plain ``str`` — and ``"thread" ==
   ConcurrencyMode.THREAD`` is False for a bare Enum. Even the CORRECT value broke it.
2. The module exists in three places and can be imported under more than one path in a
   merged OSS+cloud tree, producing two distinct ``ConcurrencyMode`` CLASSES. Members
   of different Enum classes never compare equal, so the guard raised for every call —
   this is what took out ~70 integration tests.

``StrEnum`` members ARE strings, so both compare by value. These tests fail if anyone
reverts it to ``Enum``.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_COPIES = [
    _ROOT / "backend" / "utils" / "local_context.py",
    _ROOT / "workers" / "shared" / "utils" / "local_context.py",
    _ROOT / "workers" / "shared" / "infrastructure" / "context.py",
]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", _COPIES, ids=lambda p: p.parent.name)
def test_mode_compares_equal_to_its_string_value(path):
    # Failure mode 1: a SET env var yields a str; it must still satisfy the guard.
    mod = _load(f"cm_str_{path.parent.name}", path)
    assert mod.ConcurrencyMode.THREAD == "thread"
    assert "thread" == mod.ConcurrencyMode.THREAD


def test_members_compare_equal_across_duplicate_module_copies():
    # Failure mode 2: the same module under two import paths => two classes. The guard
    # must still hold, or every StateStore call raises in a merged tree.
    a = _load("cm_dup_a", _COPIES[0])
    b = _load("cm_dup_b", _COPIES[1])
    assert a.ConcurrencyMode is not b.ConcurrencyMode  # genuinely distinct classes
    assert a.ConcurrencyMode.THREAD == b.ConcurrencyMode.THREAD


def test_state_store_round_trips_with_env_var_set(monkeypatch):
    # End-to-end: the exact call that raised in CI.
    monkeypatch.setenv("CONCURRENCY_MODE", "thread")
    mod = _load("cm_env", _COPIES[0])
    assert mod.StateStore.mode == mod.ConcurrencyMode.THREAD
    mod.StateStore.set("organization_id", "org-1")
    assert mod.StateStore.get("organization_id") == "org-1"
    mod.StateStore.clear("organization_id")
