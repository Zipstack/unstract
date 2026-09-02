"""Scrubbed-env, rlimit-bounded subprocess harness for sandboxed code.

Enforces spec §6.3 layers 1-2 in-process (the pod supplies layers 3-5). The
child is invoked as ``python -I -S -E <script> <input_path> <output_path>``
with an EMPTY environment (minimal PATH only), a fresh session/process group,
and rlimits on CPU / address space / PIDs / open files / output size.

Two independent kill mechanisms bound runaway children:

- **Primary — wall-clock timeout.** ``Popen.communicate(timeout=timeout)``
  is the deterministic path: at ``timeout`` wall-clock seconds we kill the
  child's whole process group (it was made a session/group leader via
  ``os.setsid()`` in ``preexec_fn``, so grandchildren die too) and return a
  "timed out" ``RunResult``.
- **Backstop — RLIMIT_CPU.** Set to ``timeout + grace`` (never less than
  ``timeout + 1``) CPU-seconds — strictly *above* the wall-clock timeout —
  so it only fires if the wall-clock path somehow fails to. Setting it equal
  to the wall-clock timeout (as a naive implementation might) would make the
  two mechanisms race at the same threshold, producing a nondeterministic
  error string ("timed out" vs. an RLIMIT_CPU/SIGXCPU exit) for the exact
  same hostile input. Keeping it strictly higher keeps the wall-clock path
  the only mechanism that fires in the common case.
"""
from __future__ import annotations

import json
import logging
import os
import resource
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sandbox.gate import check_code_safe

logger = logging.getLogger(__name__)

_MINIMAL_PATH = "/usr/bin:/bin"
_CAPTURE_LIMIT = 4096
_SANDBOX_PLACEHOLDER = "<sandbox>"


def _scrub(text: str, tmp: str) -> str:
    """Replace the per-run tempdir's host path with a fixed placeholder.

    A script that raises writes a traceback containing the real host path
    to ``script.py`` (e.g. ``File "/var/folders/.../sandbox_xxxx/script.py"``)
    into stdout/stderr, which run_code returns to the caller. Errors must
    stay user-safe: no host filesystem paths leak, while the rest of the
    message (exception type, line, syntax-error text, etc.) stays intact
    for debuggability.
    """
    if not text:
        return text
    return text.replace(tmp, _SANDBOX_PLACEHOLDER)


@dataclass
class RunResult:
    success: bool
    rows_jsonl: str = ""
    rows_written: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


def _limits(cpu_seconds: int, memory_mb: int, max_pids: int, fsize: int):
    """Build a ``preexec_fn`` that applies rlimits and detaches the child
    into its own session so a group kill can reap any grandchildren it
    spawns. Each rlimit is best-effort: a platform that lacks one (e.g.
    RLIMIT_NPROC is not honoured the same way on every POSIX system) must
    not prevent the harness from applying the rest.
    """

    def _apply():
        os.setsid()
        for limit, value in (
            (resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds)),
            (resource.RLIMIT_AS, (memory_mb * 1024 * 1024, memory_mb * 1024 * 1024)),
            (resource.RLIMIT_NPROC, (max_pids, max_pids)),
            (resource.RLIMIT_FSIZE, (fsize, fsize)),
            (resource.RLIMIT_NOFILE, (64, 64)),
        ):
            try:
                resource.setrlimit(limit, value)
            except (ValueError, OSError):
                # Not honoured on this platform/kernel — skip, keep the rest.
                pass

    return _apply


def run_code(
    code: str,
    input_json: str,
    *,
    timeout: int,
    max_output_bytes: int,
    max_rows: int,
    memory_mb: int,
    max_pids: int,
    grace: int = 5,
) -> RunResult:
    """Re-check the safety gate, then run ``code`` as a child process.

    The gate is re-run here unconditionally — the caller having already
    checked it is never trusted. On a gate rejection nothing is executed.
    """
    ok, reason = check_code_safe(code)
    if not ok:
        return RunResult(success=False, error=reason)

    # RLIMIT_CPU backstop, strictly above the wall-clock timeout (ruling
    # R1): equal thresholds make the two kill mechanisms race and produce a
    # nondeterministic error string for the same input.
    cpu_seconds = max(timeout + grace, timeout + 1)

    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmp:
        d = Path(tmp)
        script = d / "script.py"
        inp = d / "input.json"
        out = d / "output.jsonl"
        script.write_text(code)
        inp.write_text(input_json)
        out.write_text("")

        proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-S", "-E", str(script), str(inp), str(out)],
                cwd=tmp,
                env={"PATH": _MINIMAL_PATH},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=_limits(cpu_seconds, memory_mb, max_pids, max_output_bytes),
            )
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            # Wall-clock deadline hit: kill the whole process group so any
            # children/grandchildren the script spawned die too (this is
            # why _limits() makes the child a session leader via
            # os.setsid() before it execs the script).
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=1)
            except Exception:
                stdout, stderr = "", ""
            return RunResult(
                success=False,
                stdout=_scrub(stdout or "", tmp)[:_CAPTURE_LIMIT],
                stderr=_scrub(stderr or "", tmp)[:_CAPTURE_LIMIT],
                error=f"execution timed out after {timeout}s",
            )
        except Exception as exc:
            # rlimit / spawn failure, or a rare non-timeout failure during
            # communicate(). Mirror the TimeoutExpired branch above: best-
            # effort kill the child's process group so a partially-started
            # child doesn't run away unsupervised. `proc` can be None here
            # (Popen itself failed to spawn), unlike in the TimeoutExpired
            # branch, so guard on that before attempting the kill.
            if proc is not None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    pass
            return RunResult(success=False, error=f"execution failed: {type(exc).__name__}")

        stdout = _scrub(stdout or "", tmp)[:_CAPTURE_LIMIT]
        stderr = _scrub(stderr or "", tmp)[:_CAPTURE_LIMIT]
        if returncode != 0:
            return RunResult(
                success=False, stdout=stdout, stderr=stderr,
                error=f"execution failed: exit {returncode}",
            )

        # The output read + JSONL parse is guarded end-to-end: `read_text` is
        # forced to UTF-8 with `errors="replace"` so bytes the child wrote
        # that aren't valid UTF-8 decode to replacement characters instead of
        # raising `UnicodeDecodeError` (which, unguarded, would propagate out
        # of run_code and break the "always return a structured RunResult"
        # contract every other failure path here honours). The broad
        # `except Exception` below is defense-in-depth for any other
        # unexpected read failure (e.g. a filesystem error) — it never masks
        # the specific size/row-cap returns above it, which `return` out of
        # the `try` rather than raise.
        try:
            raw = out.read_text(encoding="utf-8", errors="replace")
            if len(raw.encode()) > max_output_bytes:
                return RunResult(success=False, stdout=stdout, stderr=stderr,
                                 error="execution failed: output exceeds size cap")
            rows = 0
            for line in raw.splitlines():
                if not line.strip():
                    continue
                json.loads(line)
                rows += 1
                if rows > max_rows:
                    return RunResult(success=False, stdout=stdout, stderr=stderr,
                                     error=f"execution failed: output exceeds row cap of {max_rows} rows")
        except ValueError:
            return RunResult(success=False, stdout=stdout, stderr=stderr,
                             error="execution failed: invalid JSONL output")
        except Exception:
            return RunResult(success=False, stdout=stdout, stderr=stderr,
                             error="execution failed: unreadable output")
        return RunResult(success=True, rows_jsonl=raw, rows_written=rows,
                         stdout=stdout, stderr=stderr)
