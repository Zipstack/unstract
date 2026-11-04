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
        # NOTE: no `os.setsid()` here. Session creation moved to Popen's
        # `start_new_session=True`, which the runtime performs between fork and
        # exec WITHOUT running Python bytecode. `preexec_fn` does run Python in
        # the forked child, and CPython documents that as unsafe when the
        # parent has threads -- this worker has at least two (the health HTTP
        # server, and the heartbeat on the supervised PG path), either of which
        # can hold the allocator or import lock at fork. The failure that buys
        # is a child that deadlocks before exec and is then reported as
        # `execution timed out after {timeout}s`: a harness fault attributed to
        # the submitted code.
        #
        # `setrlimit` is still here because there is no Popen keyword for it.
        # That is a narrower exposure than setsid + setrlimit, not zero.
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


def _pgid_of(proc) -> int | None:
    """The child's process-group id, read while the child is still alive.

    Captured once, right after the spawn, so the failure paths below read the
    pgid a single time rather than re-reading it from a child that may already
    have been reaped (where `os.getpgid` fails with ESRCH). Returns None when
    the child is already gone, which `_kill_group` treats as nothing to kill.
    """
    try:
        return os.getpgid(proc.pid)
    except Exception:
        return None


def _kill_group(pgid: int | None, note: str) -> None:
    """SIGKILL a whole process group, best effort.

    The group (not just the pid) because _limits() makes the child a session
    leader via os.setsid() before it execs, so any children/grandchildren the
    script spawned die with it. Failures are logged, never raised: every caller
    is already returning a failure RunResult.

    ProcessLookupError is swallowed WITHOUT logging: the group being gone
    already is an ordinary race with the child exiting on its own, not a
    problem worth a line in the worker log.

    pgid <= 1 and our own group are refused outright: killpg(1, ...) is
    kill(-1, ...), which SIGKILLs every process this user owns (a MagicMock
    proc in tests has pid 1 via __index__), and our own group is the worker.
    """
    if pgid is None or pgid <= 1 or pgid == os.getpgrp():
        return
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception:
        logger.warning(note, exc_info=True)


def _reap(proc) -> None:
    """Wait briefly for a SIGKILLed child so it does not linger as a zombie."""
    try:
        proc.wait(timeout=5)
    except Exception:
        logger.warning(
            "sandbox: timed-out child did not exit after SIGKILL",
            exc_info=True,
        )


def _result_from_output(
    out: Path,
    *,
    max_output_bytes: int,
    max_rows: int,
    stdout: str,
    stderr: str,
) -> RunResult:
    """Read the script's output.jsonl and turn it into the final RunResult.

    Guarded end-to-end: `read_text` is forced to UTF-8 with `errors="replace"`
    so bytes the child wrote that aren't valid UTF-8 decode to replacement
    characters instead of raising `UnicodeDecodeError` (which, unguarded, would
    propagate out of run_code and break the "always return a structured
    RunResult" contract every other failure path honours). The broad
    `except Exception` is defense-in-depth for any other unexpected read
    failure (e.g. a filesystem error) -- it never masks the specific
    size/row-cap returns above it, which `return` out of the `try` rather
    than raise.
    """
    try:
        raw = out.read_text(encoding="utf-8", errors="replace")
        if len(raw.encode()) > max_output_bytes:
            return RunResult(
                success=False,
                stdout=stdout,
                stderr=stderr,
                error="execution failed: output exceeds size cap",
            )
        rows = 0
        # `split("\n")`, NOT `splitlines()`. JSONL is newline-delimited, and
        # `splitlines()` also breaks on NEL (U+0085), LINE SEPARATOR (U+2028)
        # and PARAGRAPH SEPARATOR (U+2029) -- which `json.dumps(...,
        # ensure_ascii=False)` emits LITERALLY inside a string, since JSON only
        # requires escaping below U+0020. So one valid row carrying any of them
        # was split into fragments, every fragment failed `json.loads`, and the
        # `except ValueError` below reported "invalid JSONL output" for output
        # that was valid. Measured: `json.dumps({"name": "first\u2028second"},
        # ensure_ascii=False)` is one row and two fragments, neither parseable.
        # The row COUNT was inflated the same way, so `max_rows` could trip on
        # a compliant file.
        #
        # Those three reach the file; the control separators splitlines() also
        # breaks on (\x0b, \x0c, \x1c-\x1e) do not, because json.dumps escapes
        # everything below U+0020 regardless of ensure_ascii. Document text
        # copied out of PDFs and word processors is where U+2028/U+2029 come
        # from, so this is reachable rather than theoretical.
        #
        # CRLF output stays safe: `split("\n")` leaves a trailing "\r", which
        # `json.loads` accepts as whitespace (checked).
        for line in raw.split("\n"):
            if not line.strip():
                continue
            json.loads(line)
            rows += 1
            if rows > max_rows:
                return RunResult(
                    success=False,
                    stdout=stdout,
                    stderr=stderr,
                    error=f"execution failed: output exceeds row cap of {max_rows} rows",
                )
    except ValueError:
        return RunResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
            error="execution failed: invalid JSONL output",
        )
    except Exception:
        return RunResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
            error="execution failed: unreadable output",
        )
    return RunResult(
        success=True, rows_jsonl=raw, rows_written=rows, stdout=stdout, stderr=stderr
    )


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
    """Guarded entry point: ALWAYS returns a structured ``RunResult``.

    The body lives in `_run_code_unguarded`. Four statements there sit outside
    its internal `try` by construction -- the gate call, the
    `TemporaryDirectory` open, the three `write_text` calls, and the tempdir's
    own cleanup -- and each can raise: the gate on a parse failure CPython
    spells as MemoryError (see `gate.check_code_safe`), the others on ENOSPC,
    which is routine on the 256 MB tmpfs this service runs with.

    Guarding each site individually is a rule a future edit has to remember.
    This wrapper is the structural version: anything escaping the body becomes
    a result rather than an exception, so the contract holds for every caller --
    including `tasks.py`, which does not wrap this call either.

    The error text is the exception TYPE only. Its message can carry a host
    path or a fragment of the generated code, and this string reaches the
    submitting caller.
    """
    try:
        return _run_code_unguarded(
            code,
            input_json,
            timeout=timeout,
            max_output_bytes=max_output_bytes,
            max_rows=max_rows,
            memory_mb=memory_mb,
            max_pids=max_pids,
            grace=grace,
        )
    except Exception as exc:
        logger.warning(
            "sandbox: run_code failed outside the guarded region: %s", exc, exc_info=True
        )
        return RunResult(success=False, error=f"execution failed: {type(exc).__name__}")


def _run_code_unguarded(
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
        # Logged, not silent. This is the most security-relevant event the
        # feature has, and layer 1 was the only layer emitting no signal for
        # it: no counter, no log line, nothing to tell a codegen-quality
        # problem (a legitimate script using a denylisted NAME) from an
        # attempted bypass. The harness-failure path below already carries a
        # log for the same reason.
        logger.warning("sandbox: gate rejected generated code: %s", reason)
        return RunResult(success=False, error=reason)

    # RLIMIT_CPU backstop, strictly above the wall-clock timeout (ruling
    # R1): equal thresholds make the two kill mechanisms race and produce a
    # nondeterministic error string for the same input.
    cpu_seconds = max(timeout + grace, timeout + 1)

    # ignore_cleanup_errors: on 3.12 __exit__ defaults to raising, so an rmtree
    # failure (ENOSPC, a child still writing) would discard an already-computed
    # RunResult and propagate -- the contract break this function exists to avoid.
    with tempfile.TemporaryDirectory(
        prefix="sandbox_", ignore_cleanup_errors=True
    ) as tmp:
        d = Path(tmp)
        script = d / "script.py"
        inp = d / "input.json"
        out = d / "output.jsonl"
        script.write_text(code)
        inp.write_text(input_json)
        # Pre-created so `_result_from_output` always has a file to read.
        #
        # KNOWN AMBIGUITY, recorded rather than fixed here: a child that exits 0
        # without writing is indistinguishable from a transform that
        # legitimately matched no rows -- both are
        # `success=True, rows_jsonl="", rows_written=0`. For LLM-generated code
        # the first is ordinary (a branch that never fires, a write to the wrong
        # path, a swallowed exception), and the caller then sees an empty
        # extraction reported as a clean success with empty stderr.
        #
        # Distinguishing them means adding a field to RunResult, which is the
        # contract the cloud `agentic_kv` engine consumes -- so the decision
        # belongs with that consumer, not here: it is what must choose whether
        # "exited 0, wrote nothing" is an error. Tracked for that side rather
        # than changed unilaterally. Note this diff applies the OPPOSITE
        # reasoning to billing (`executor/tasks.py`: "a successful run emitting
        # nothing is unambiguously a broken chain"), which is the asymmetry to
        # resolve when it is picked up.
        out.write_text("")

        # Child stdout/stderr go to FILES in the per-job tempdir, not pipes.
        # `communicate()` buffers the child's full output in the PARENT's
        # memory and the `[:_CAPTURE_LIMIT]` truncation happens after, so
        # `while True: print('A'*100000)` -- no imports, passes the gate
        # trivially -- streamed gigabytes into this process and could OOM the
        # worker before the wall-clock timeout fired. A gate-agnostic DoS.
        #
        # Files make the EXISTING rlimit bite: RLIMIT_FSIZE is already set to
        # `max_output_bytes` but does not apply to pipes, so a child writing to
        # a file gets SIGXFSZ at the limit instead. The parent then reads back
        # at most `_CAPTURE_LIMIT`, so its memory is bounded by that constant
        # rather than by the child's behaviour.
        #
        # RLIMIT_FSIZE applies to every file the child writes, so stdout.txt,
        # stderr.txt and output.jsonl are each capped at `max_output_bytes`.
        # PER FILE, not in total: the limit bounds each file's maximum offset
        # and nothing bounds their sum. The only total bound is the tmpfs the
        # service mounts (256 MiB in compose), which is why that cap exists and
        # is not redundant with this one -- size it against the per-file limit
        # times the number of files a job can create, not against this value.
        stdout_path = d / "stdout.txt"
        stderr_path = d / "stderr.txt"

        def _captured() -> tuple[str, str]:
            """Read back both streams, each capped, tolerant of a missing file."""
            texts = []
            for path in (stdout_path, stderr_path):
                try:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        texts.append(fh.read(_CAPTURE_LIMIT))
                except OSError:
                    texts.append("")
            return texts[0], texts[1]

        proc = None
        # Initialised here so the failure paths can use the ONE pgid captured
        # after the spawn: calling _pgid_of again there would read it a second
        # time (and read it from an already-reaped child).
        pgid = None
        try:
            with open(stdout_path, "w") as f_out, open(stderr_path, "w") as f_err:
                proc = subprocess.Popen(
                    [sys.executable, "-I", "-S", "-E", str(script), str(inp), str(out)],
                    cwd=tmp,
                    env={"PATH": _MINIMAL_PATH},
                    stdout=f_out,
                    stderr=f_err,
                    text=True,
                    # The session-leader half of the old `preexec_fn`, done by
                    # the runtime rather than by Python bytecode post-fork.
                    # `_kill_group` depends on the child being a session leader.
                    start_new_session=True,
                    preexec_fn=_limits(
                        cpu_seconds, memory_mb, max_pids, max_output_bytes
                    ),
                )
                # Captured BEFORE the wait: by the time a failure path runs,
                # the child may already be reaped and its pgid unreadable.
                pgid = _pgid_of(proc)
                proc.wait(timeout=timeout)
            stdout, stderr = _captured()
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            # Wall-clock deadline hit: kill the whole process group so any
            # children/grandchildren the script spawned die too (this is
            # why _limits() makes the child a session leader via
            # os.setsid() before it execs the script).
            _kill_group(
                pgid, "sandbox: could not kill the timed-out child's process group"
            )
            # REAP before reading. SIGKILL is asynchronous: without this the
            # child may still be writing when the capture files are read
            # (truncated diagnostics) and, worse, is left unreaped in a
            # long-lived worker -- a zombie per timed-out job. The pre-review
            # code got this incidentally from `communicate(timeout=1)`; moving
            # to files dropped the wait with it.
            _reap(proc)
            stdout, stderr = _captured()
            return RunResult(
                success=False,
                stdout=_scrub(stdout, tmp)[:_CAPTURE_LIMIT],
                stderr=_scrub(stderr, tmp)[:_CAPTURE_LIMIT],
                error=f"execution timed out after {timeout}s",
            )
        except Exception as exc:
            # rlimit / spawn failure, or a rare non-timeout failure during
            # communicate(). Mirror the TimeoutExpired branch above: best-
            # effort kill the child's process group so a partially-started
            # child doesn't run away unsupervised. `proc` can be None here
            # (Popen itself failed to spawn), unlike in the TimeoutExpired
            # branch, so guard on that before attempting the kill.
            # Logged, not silent: both broad `except` blocks here used to
            # swallow the cause entirely, so an OSError or a fork EAGAIN was
            # reported to the engine as an ordinary codegen failure with
            # nothing anywhere to say the harness itself had failed.
            logger.warning("sandbox: harness failure running generated code: %s", exc)
            if proc is not None:
                _kill_group(pgid, "sandbox: could not kill the child's process group")
                # Reap, for the same reason the timeout branch above does:
                # SIGKILL is asynchronous, so without the wait the child is
                # left a zombie -- one per occurrence in a long-lived worker --
                # and `TemporaryDirectory.__exit__` can rmtree the per-job
                # directory while a not-yet-dead child is still writing into it.
                _reap(proc)
            return RunResult(
                success=False, error=f"execution failed: {type(exc).__name__}"
            )

        stdout = _scrub(stdout or "", tmp)[:_CAPTURE_LIMIT]
        stderr = _scrub(stderr or "", tmp)[:_CAPTURE_LIMIT]
        if returncode != 0:
            return RunResult(
                success=False,
                stdout=stdout,
                stderr=stderr,
                error=f"execution failed: exit {returncode}",
            )

        return _result_from_output(
            out,
            max_output_bytes=max_output_bytes,
            max_rows=max_rows,
            stdout=stdout,
            stderr=stderr,
        )
