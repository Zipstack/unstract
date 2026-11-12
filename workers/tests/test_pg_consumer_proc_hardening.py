"""The dumpable-flag hardening on pools that execute untrusted code (R12).

Two layers, deliberately:

* unit tests over the gate and the failure paths, with ``prctl`` mocked;
* one end-to-end test that spawns a real launcher, a real "generated script"
  child under the same UID, and asserts the child CANNOT read the launcher's
  ``/proc/<ppid>/environ``. Its negative control asserts the same child DOES
  recover ``DB_PASSWORD`` when the gate is off — without that control a test
  asserting "blocked" would pass just as happily against a child that never
  managed to read anything for an unrelated reason.
"""

import ctypes
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pg_queue_consumer import _bootstrap
from pg_queue_consumer._bootstrap import (
    _PR_SET_DUMPABLE,
    _SUID_DUMP_DISABLE,
    drop_dumpable_for_untrusted_code_pools,
)

_MOD = "pg_queue_consumer._bootstrap"
_TYPE_ENV = "WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE"

# The launcher stands in for `python -m pg_queue_consumer`: harden, then spawn
# the generated script exactly as `sandbox/runner.py` does -- scrubbed env, new
# session, same UID.
_LAUNCHER = textwrap.dedent(
    """
    import subprocess, sys
    from pg_queue_consumer._bootstrap import drop_dumpable_for_untrusted_code_pools

    drop_dumpable_for_untrusted_code_pools()
    done = subprocess.run(
        [sys.executable, "-I", "-S", "-E", sys.argv[1]],
        env={"PATH": "/usr/bin:/bin"},
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        start_new_session=True,
        timeout=60,
    )
    sys.stdout.write(done.stdout.strip() + "\\n")
    sys.stderr.write(done.stderr[-400:])
    """
)

# Only `open()` and string ops -- precisely what the AST gate permits by design.
_GENERATED_SCRIPT = textwrap.dedent(
    """
    with open("/proc/self/stat") as f:
        ppid = f.read().split()[3]
    try:
        with open("/proc/" + ppid + "/environ", "rb") as f:
            blob = f.read()
    except OSError:
        print("BLOCKED")
    else:
        hit = [kv for kv in blob.split(bytes([0])) if kv.startswith(b"DB_PASSWORD=")]
        print("LEAKED" if hit else "ENV_HELD_NO_SECRET")
    """
)


class TestTheGateChoosesWhichPoolsAreHardened:
    def test_the_sandbox_pool_clears_the_flag(self, monkeypatch):
        monkeypatch.setenv(_TYPE_ENV, "sandbox")
        prctl = MagicMock(return_value=0)
        with patch(f"{_MOD}._resolve_prctl", return_value=prctl):
            drop_dumpable_for_untrusted_code_pools()
        prctl.assert_called_once_with(_PR_SET_DUMPABLE, _SUID_DUMP_DISABLE, 0, 0, 0)

    def test_the_constants_are_the_kernels_and_not_placeholders(self):
        # PR_SET_DUMPABLE=4 / SUID_DUMP_DISABLE=0 from prctl(2). Pinned because
        # a wrong-but-plausible pair would still return 0 for some other prctl
        # operation, and the mocked tests above could not tell the difference.
        assert (_PR_SET_DUMPABLE, _SUID_DUMP_DISABLE) == (4, 0)

    @pytest.mark.parametrize("worker_type", ["notification", "general", "executor", ""])
    def test_every_other_pool_is_left_alone(self, monkeypatch, worker_type):
        monkeypatch.setenv(_TYPE_ENV, worker_type)
        resolve = MagicMock()
        with patch(f"{_MOD}._resolve_prctl", resolve):
            drop_dumpable_for_untrusted_code_pools()
        # Not merely "prctl not called" -- the resolver must not even run, so an
        # unrelated pool pays no dlsym on every start.
        resolve.assert_not_called()

    def test_an_unset_worker_type_is_left_alone(self, monkeypatch):
        monkeypatch.delenv(_TYPE_ENV, raising=False)
        resolve = MagicMock()
        with patch(f"{_MOD}._resolve_prctl", resolve):
            drop_dumpable_for_untrusted_code_pools()
        resolve.assert_not_called()

    def test_the_gate_reads_the_chart_env_not_the_derived_worker_type(self, monkeypatch):
        # `select_source_worker_type` has NOT necessarily run when this is
        # called -- on the supervisor path it runs per forked child. Reading
        # WORKER_TYPE instead would silently no-op on exactly the pool that
        # needs hardening.
        monkeypatch.delenv(_TYPE_ENV, raising=False)
        monkeypatch.setenv("WORKER_TYPE", "sandbox")
        resolve = MagicMock()
        with patch(f"{_MOD}._resolve_prctl", resolve):
            drop_dumpable_for_untrusted_code_pools()
        resolve.assert_not_called()


class TestAFailureToHardenIsLoudButNotFatal:
    def test_an_unresolvable_prctl_warns_and_returns(self, monkeypatch, caplog):
        monkeypatch.setenv(_TYPE_ENV, "sandbox")
        with patch(f"{_MOD}._resolve_prctl", return_value=None):
            with caplog.at_level("WARNING"):
                drop_dumpable_for_untrusted_code_pools()
        assert "prctl could not be resolved" in caplog.text
        assert "R12" in caplog.text

    def test_a_failing_prctl_warns_with_errno_and_returns(self, monkeypatch, caplog):
        monkeypatch.setenv(_TYPE_ENV, "sandbox")
        prctl = MagicMock(return_value=-1)
        with patch(f"{_MOD}._resolve_prctl", return_value=prctl):
            with patch.object(ctypes, "get_errno", return_value=1):
                with caplog.at_level("WARNING"):
                    drop_dumpable_for_untrusted_code_pools()
        assert "PR_SET_DUMPABLE failed" in caplog.text
        assert "errno=1" in caplog.text

    def test_resolution_off_linux_is_silent_rather_than_a_warning(self, monkeypatch):
        # An absent Linux facility off Linux is expected, not misconfiguration.
        monkeypatch.setattr(_bootstrap.sys, "platform", "darwin")
        assert _bootstrap._resolve_prctl() is None

    def test_resolution_on_linux_binds_a_callable(self):
        if not sys.platform.startswith("linux"):
            pytest.skip("prctl is a Linux facility")
        assert _bootstrap._resolve_prctl() is not None


@pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="/proc and prctl are Linux facilities"
)
class TestAGeneratedScriptCannotReadTheLaunchersEnvironment:
    """The guarantee itself, by execution rather than by mock."""

    @staticmethod
    def _run(tmp_path: Path, worker_type: str) -> str:
        launcher = tmp_path / "launcher.py"
        launcher.write_text(_LAUNCHER)
        script = tmp_path / "generated.py"
        script.write_text(_GENERATED_SCRIPT)
        workers_root = Path(_bootstrap.__file__).resolve().parents[1]
        done = subprocess.run(
            [sys.executable, str(launcher), str(script)],
            cwd=tmp_path,
            env={
                "PATH": "/usr/bin:/bin",
                "PYTHONPATH": str(workers_root),
                _TYPE_ENV: worker_type,
                # Stands in for the `database` shared-config group the sandbox
                # pool mounts. Must be in the INITIAL env: /proc/<pid>/environ
                # reflects the exec-time stack, not later os.environ edits.
                "DB_PASSWORD": "not-a-real-password-fixture",
                "DB_USER": "postgres",
            },
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert done.returncode == 0, f"launcher failed: {done.stderr[-800:]}"
        return done.stdout.strip()

    def test_the_read_is_refused_on_the_sandbox_pool(self, tmp_path):
        assert self._run(tmp_path, "sandbox") == "BLOCKED"

    def test_control_the_same_read_succeeds_when_the_pool_is_not_hardened(self, tmp_path):
        # The control that gives the assertion above its meaning: the attack
        # works, and the hardening is what stops it.
        assert self._run(tmp_path, "notification") == "LEAKED"
