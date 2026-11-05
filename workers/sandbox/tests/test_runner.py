import json
import os
import resource
import signal
import subprocess
import time
from unittest.mock import MagicMock, patch

from sandbox.runner import _MINIMAL_PATH, run_code

_DEFAULTS = dict(
    timeout=10,
    max_output_bytes=1_048_576,
    max_rows=100_000,
    memory_mb=512,
    max_pids=16,
    grace=5,
)

# The runner contract: argv[1]=input json path, argv[2]=output jsonl path.
_ECHO = (
    "import json, sys\n"
    "data = json.load(open(sys.argv[1]))\n"
    "rec = data['records'][0]\n"
    "with open(sys.argv[2], 'w') as f:\n"
    "    f.write(json.dumps({'doubled': rec['n'] * 2}) + '\\n')\n"
)


def test_happy_transform():
    r = run_code(_ECHO, json.dumps({"records": [{"n": 21}]}), **_DEFAULTS)
    assert r.success is True, r.error
    assert r.rows_written == 1
    assert json.loads(r.rows_jsonl.strip()) == {"doubled": 42}


def test_gate_rejects_before_running():
    r = run_code("import os\nos.system('id')", "{}", **_DEFAULTS)
    assert r.success is False
    assert r.error.startswith("safety gate:")


def test_infinite_loop_times_out():
    r = run_code("while True:\n    pass\n", "{}", **{**_DEFAULTS, "timeout": 2})
    assert r.success is False
    # Wall-clock subprocess.run(timeout=) is the primary kill mechanism; the
    # RLIMIT_CPU backstop (set strictly above the wall-clock timeout per
    # ruling R1) only fires in rare cases, so tolerate either error shape.
    err = r.error.lower()
    assert "timed out" in err or "killed" in err or "exit" in err


def test_infinite_loop_kill_is_prompt_not_backstop():
    # A liveness smoke test, and named for what it actually proves: the child
    # is killed rather than left to run, and it happens within the budget.
    #
    # It does NOT pin ruling R1 -- `elapsed < timeout + grace` holds whether
    # RLIMIT_CPU is `timeout + grace` or `timeout`, so this test passed
    # unchanged under the mutation `cpu_seconds = timeout`. The threshold
    # itself is pinned by
    # `test_rlimit_cpu_is_set_strictly_above_the_wall_clock_timeout` below.
    timeout, grace = 2, 5
    started = time.monotonic()
    r = run_code(
        "while True:\n    pass\n",
        "{}",
        **{**_DEFAULTS, "timeout": timeout, "grace": grace},
    )
    elapsed = time.monotonic() - started
    assert r.success is False
    assert elapsed < timeout + grace


def test_rlimit_cpu_is_set_strictly_above_the_wall_clock_timeout():
    """Ruling R1, asserted on the threshold rather than on elapsed time.

    RLIMIT_CPU must be a BACKSTOP, strictly above the wall-clock timeout. Set
    equal to it, the two mechanisms race at the same threshold and the same
    hostile input yields a nondeterministic error string -- which is why
    `test_infinite_loop_times_out` above has to tolerate three different error
    shapes. That tolerance is the symptom; this is the guard.

    Fails under `cpu_seconds = timeout`, which the elapsed-time test above
    does not.
    """
    timeout, grace = 2, 5
    calls = []

    def _record(which, pair):
        calls.append((which, pair))

    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.returncode = 0
    with (
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc) as mock_popen,
        patch("sandbox.runner.os.getpgid", return_value=4321),
        patch("sandbox.runner.os.killpg"),
    ):
        run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}),
            **{**_DEFAULTS, "timeout": timeout, "grace": grace},
        )
        # `preexec_fn` is never executed by a mocked Popen, so call it here
        # with setrlimit captured. That is the only way to read the pairs the
        # child would have been given.
        preexec = mock_popen.call_args.kwargs["preexec_fn"]
        with patch("sandbox.runner.resource.setrlimit", side_effect=_record):
            preexec()

    cpu = dict(calls)[resource.RLIMIT_CPU]
    assert cpu == (timeout + grace, timeout + grace), calls
    assert cpu[0] > timeout, "RLIMIT_CPU must be strictly above the wall clock"


def test_the_timed_out_child_is_reaped_before_the_tempdir_is_removed():
    """The `_reap` on the timeout path, which nothing asserted.

    SIGKILL is asynchronous. Without the wait, each timed-out job leaves a
    zombie in a long-lived worker, and `TemporaryDirectory.__exit__` can
    rmtree the per-job directory while a not-yet-dead child is still writing
    into it. The comment at that call site records that this wait was already
    lost once, when the harness moved off `communicate(timeout=...)` -- so it
    needs a guard, or the same edit silently undoes it again.
    """
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.returncode = -9
    # First wait is the wall-clock deadline; the second is the reap.
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired("x", 2), 0]
    with (
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc),
        patch("sandbox.runner.os.getpgid", return_value=4321),
        patch("sandbox.runner.os.killpg") as mock_killpg,
    ):
        r = run_code(
            "while True:\n    pass\n",
            "{}",
            **{**_DEFAULTS, "timeout": 2},
        )
    assert r.success is False
    assert "timed out" in r.error
    mock_killpg.assert_called_once_with(4321, signal.SIGKILL)
    assert mock_proc.wait.call_count == 2, "the child was killed but never reaped"
    assert mock_proc.wait.call_args.kwargs == {"timeout": 5}


def test_the_output_byte_cap_is_enforced_on_the_file_size(tmp_path):
    """The byte cap had no test at all; its row-cap sibling did.

    A UNIT test of `_result_from_output`, deliberately, and the reason is the
    finding itself: `max_output_bytes` is also the child's `RLIMIT_FSIZE`, so
    a child that tries to exceed the cap dies on the write and is reported as
    `exit N` with a truncated file -- an end-to-end attempt returns
    `invalid JSONL output`, never `size cap`. The parent-side check is a
    second line of defence against a file that is already too big, so the only
    honest way to reach it is to hand it one.

    Measured on `out.stat().st_size`, not on the re-encoded decode: with
    `errors="replace"` each undecodable byte costs 3 bytes back, so the old
    `len(raw.encode())` form measured up to 3x the file and refused files that
    were within the cap.
    """
    from sandbox.runner import _result_from_output

    out = tmp_path / "output.jsonl"
    out.write_text(json.dumps({"k": "a" * 4000}) + "\n")
    r = _result_from_output(out, max_output_bytes=512, max_rows=100, stdout="", stderr="")
    assert r.success is False
    assert "size cap" in r.error, r.error


def test_a_non_utf8_file_within_the_cap_is_accepted_when_it_does_not_inflate(tmp_path):
    """Undecodable bytes alone are not a reason to refuse.

    This is the half of the original defect that still stands: a file
    comfortably inside the cap must not be refused just because it is not
    valid UTF-8. Fails if the returned-payload check below is applied to the
    file size, or if the file check is restored to the inflated length.
    """
    from sandbox.runner import _result_from_output

    out = tmp_path / "output.jsonl"
    # 3 undecodable bytes -> 9 after replacement; well inside a 4096 cap either way.
    out.write_bytes(b'{"k": "' + b"\xff\xfe\xfd" + b'aaa"}\n')
    r = _result_from_output(
        out, max_output_bytes=4096, max_rows=100, stdout="", stderr=""
    )
    assert r.success is True, r.error


def test_a_non_utf8_file_that_inflates_past_the_cap_names_the_encoding(tmp_path):
    """The two causes must be distinguishable by the caller.

    An earlier revision measured the cap on the re-encoded decode ONLY, so a
    compliant file was told to shrink. The fix measured the file ONLY, which
    then let the RETURNED string carry ~3x the budget (measured: a 308-byte
    file of invalid bytes comes back as 908). Both checks now exist, and this
    pins that the inflation case names the encoding rather than reporting a
    bare "too big" -- the complaint that started this.
    """
    from sandbox.runner import _result_from_output

    out = tmp_path / "output.jsonl"
    out.write_bytes(b'{"k": "' + b"\xff" * 300 + b'"}\n')
    r = _result_from_output(out, max_output_bytes=320, max_rows=100, stdout="", stderr="")
    assert r.success is False
    assert "not valid UTF-8" in r.error, r.error


def test_subprocess_env_is_scrubbed():
    """Behavioural proof that the child's OWN environment is the minimal one.

    The previous version of this test ran a script that read no environment at
    all and asserted only `r.success is True`. It passed against a runner
    mutated to `env={**os.environ, "PATH": _MINIMAL_PATH}` -- the guard it
    advertised was not the guard it applied.

    This reads the child's `/proc/self/environ` and asserts a marker set in the
    PARENT is absent from it. Note the scope: the child's own env is scrubbed
    and that is what this pins. The parent's env remains readable via
    `/proc/<ppid>/environ` -- that is R12 (UN-4218), deliberately not this
    test's subject.
    """
    marker = "UNSTRACT_SCRUB_MARKER_7F3C"
    code = (
        "import json, sys\n"
        "with open('/proc/self/environ', 'rb') as f:\n"
        "    blob = f.read().decode('utf-8', 'replace')\n"
        "with open(sys.argv[2], 'w') as f:\n"
        "    f.write(json.dumps({'env': blob}) + '\\n')\n"
    )
    os.environ[marker] = "leaked"
    try:
        r = run_code(code, json.dumps({"records": [{}]}), **_DEFAULTS)
    finally:
        os.environ.pop(marker, None)
    assert r.success is True, r.error
    assert marker not in r.rows_jsonl, "parent env leaked into the child"
    # Prove the read saw a real environment block. Without this, a script that
    # silently read nothing would pass as a clean scrub.
    assert "PATH=" in r.rows_jsonl, r.rows_jsonl[:200]


def test_subprocess_popen_env_is_exactly_minimal_path():
    # Strengthen the behavioural scrub test above with a direct assertion on
    # the actual Popen call: the child's env must be exactly the minimal
    # PATH-only mapping — nothing from the parent's environment leaks in.
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.returncode = 0
    with (
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc) as mock_popen,
        patch("sandbox.runner.os.getpgid", return_value=4321),
        patch("sandbox.runner.os.killpg"),
    ):
        r = run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}),
            **_DEFAULTS,
        )
    assert r.success is True, r.error
    assert mock_popen.call_args.kwargs["env"] == {"PATH": _MINIMAL_PATH}


def test_non_timeout_exception_kills_process_group():
    # A rare non-timeout failure during communicate() (e.g. a transient OS
    # error) must not leave the child's process group running unsupervised.
    # Mirrors the TimeoutExpired kill path.
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    # `wait`, not `communicate`: the harness no longer pipes the child's
    # output through the parent's memory. stdout/stderr go to files in the
    # per-job tempdir so RLIMIT_FSIZE (which does not apply to pipes) bounds
    # them, and the parent reads back at most _CAPTURE_LIMIT.
    mock_proc.wait.side_effect = OSError("boom")
    with (
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc),
        patch("sandbox.runner.os.getpgid", return_value=4321) as mock_getpgid,
        patch("sandbox.runner.os.killpg") as mock_killpg,
    ):
        r = run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}),
            **_DEFAULTS,
        )
    assert r.success is False
    assert "OSError" in r.error
    mock_getpgid.assert_called_once_with(4321)
    mock_killpg.assert_called_once_with(4321, signal.SIGKILL)


def test_non_json_output_is_error():
    r = run_code(
        "import sys\nopen(sys.argv[2],'w').write('not json\\n')\n",
        json.dumps({"records": [{}]}),
        **_DEFAULTS,
    )
    assert r.success is False
    assert "invalid" in r.error.lower() or "json" in r.error.lower()


def test_unicode_line_separators_inside_a_json_string_do_not_split_the_row():
    """One valid JSONL row carrying U+2028 must stay one row.

    `splitlines()` breaks on NEL (U+0085), LINE SEPARATOR (U+2028) and
    PARAGRAPH SEPARATOR (U+2029), which `json.dumps(..., ensure_ascii=False)`
    writes LITERALLY because JSON only requires escaping below U+0020. So a
    compliant row containing any of them was split into fragments, every
    fragment failed `json.loads`, and the runner reported "invalid JSONL
    output" for output that was valid -- while also counting each fragment
    against `max_rows`.

    Document text copied out of PDFs and word processors is where these come
    from, so a calculation that preserves a cell value hits it. Found in review
    on Zipstack/unstract#2309.
    """
    code = (
        "import json, sys\n"
        "with open(sys.argv[2], 'w', encoding='utf-8') as f:\n"
        "    f.write(json.dumps({'name': 'first\u2028second'}, "
        "ensure_ascii=False) + '\\n')\n"
        "    f.write(json.dumps({'name': 'a\u2029b'}, "
        "ensure_ascii=False) + '\\n')\n"
        "    f.write(json.dumps({'name': 'c\u0085d'}, "
        "ensure_ascii=False) + '\\n')\n"
    )
    # max_rows 3 is deliberately exact: under splitlines() these three rows
    # become six fragments, so the cap would trip even if every fragment
    # somehow parsed. It pins the count as well as the parse.
    r = run_code(code, "{}", **{**_DEFAULTS, "max_rows": 3})
    assert r.success is True, r.error


def test_crlf_output_still_parses():
    r"""The one regression risk in moving off `splitlines()`.

    `split("\n")` leaves a trailing "\r" on CRLF output where `splitlines()`
    would have stripped it. `json.loads` accepts it as trailing whitespace, so
    nothing breaks -- pinned rather than assumed.
    """
    code = (
        "import sys\n"
        "with open(sys.argv[2], 'w', newline='') as f:\n"
        '    f.write(\'{"a": 1}\\r\\n{"b": 2}\\r\\n\')\n'
    )
    r = run_code(code, "{}", **_DEFAULTS)
    assert r.success is True, r.error


def test_output_row_cap_enforced():
    code = (
        "import sys\n"
        "with open(sys.argv[2], 'w') as f:\n"
        "    for i in range(10):\n"
        "        f.write('{\"i\": %d}\\n' % i)\n"
    )
    r = run_code(code, "{}", **{**_DEFAULTS, "max_rows": 3})
    assert r.success is False
    assert "rows" in r.error.lower()


def test_invalid_utf8_output_does_not_raise_and_returns_user_safe_error():
    # Non-decodable bytes in the output file must never raise UnicodeDecodeError
    # out of run_code -- the "always return a structured RunResult" contract
    # holds even when the child writes bytes invalid in the read encoding.
    code = (
        "import sys\n"
        "with open(sys.argv[2], 'wb') as f:\n"
        "    f.write(b'\\xff\\xfe not valid utf-8\\n')\n"
    )
    r = run_code(code, "{}", **_DEFAULTS)
    assert r.success is False
    assert r.error is not None
    assert r.error.startswith("execution failed:")


def test_output_read_failure_is_user_safe_unreadable_output_error():
    # Any other unexpected exception while reading/parsing the output file
    # (not just a decode issue) must also degrade to a structured, user-safe
    # failure rather than propagate.
    with patch("sandbox.runner.Path.read_text", side_effect=OSError("boom")):
        r = run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}),
            **_DEFAULTS,
        )
    assert r.success is False
    assert r.error == "execution failed: unreadable output"


def test_exception_traceback_scrubs_host_path():
    # A script that raises writes a traceback naming the real host path to
    # script.py into stderr. That must never reach the caller: the tempdir
    # path is replaced with a fixed placeholder, everything else (exception
    # type/message) stays for debuggability.
    r = run_code("raise ValueError('boom')\n", "{}", **_DEFAULTS)
    assert r.success is False
    assert "<sandbox>" in r.stderr
    assert "/var/folders" not in r.stderr
    assert "/tmp/sandbox_" not in r.stderr
    assert "boom" in r.stderr


def test_runaway_stdout_does_not_buffer_into_the_parent():
    """Gate-agnostic DoS: `while True: print(...)` imports nothing and passes
    the AST gate trivially. It used to stream into the parent's memory via
    `communicate()` (the `[:_CAPTURE_LIMIT]` truncation happened afterwards),
    so it could OOM the worker before the wall-clock timeout fired --
    RLIMIT_FSIZE does not apply to pipes and RLIMIT_AS bounds only the child.

    Output now goes to a file, where RLIMIT_FSIZE bites, and the parent reads
    back at most _CAPTURE_LIMIT.

    This is the end-to-end smoke run. It is NOT on its own proof of the fix:
    the length assertions below were equally true of the pre-fix code, which
    truncated to _CAPTURE_LIMIT only AFTER `communicate()` had buffered the
    whole stream (measured: ~1 GB resident, this test green). The decisive
    assertion lives in `test_the_childs_stdout_is_a_file_not_a_pipe`.
    """
    r = run_code(
        "import sys\n"
        "for _ in range(100000):\n"
        "    print('A' * 10000)\n"
        "open(sys.argv[2], 'w').close()\n",
        json.dumps({"records": [{}]}),
        **{**_DEFAULTS, "max_output_bytes": 65536},
    )
    assert len(r.stdout) <= 4096
    assert len(r.stderr) <= 4096


def test_stdout_is_still_captured_for_an_ordinary_script():
    """The bound must not cost us diagnostics on the normal path."""
    r = run_code(
        "import sys\nprint('hello from the sandbox')\nopen(sys.argv[2], 'w').close()\n",
        json.dumps({"records": [{}]}),
        **_DEFAULTS,
    )
    assert "hello from the sandbox" in r.stdout


def test_the_childs_stdout_is_a_file_not_a_pipe():
    """The assertion that actually distinguishes the pipe->file change.

    `test_runaway_stdout_does_not_buffer_into_the_parent` bounds what the
    parent RETURNS; the pre-fix code bounded that too. What changed is what the
    parent HOLDS, and that is decided by the `stdout`/`stderr` kwargs: a real
    file descriptor means the kernel writes to disk (where RLIMIT_FSIZE bites),
    while `subprocess.PIPE` means the parent buffers.
    """
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.returncode = 0
    with (
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc) as mock_popen,
        patch("sandbox.runner.os.getpgid", return_value=4321),
        patch("sandbox.runner.os.killpg"),
    ):
        run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}),
            **_DEFAULTS,
        )
    kw = mock_popen.call_args.kwargs
    for stream in ("stdout", "stderr"):
        assert (
            kw[stream] is not subprocess.PIPE
        ), f"{stream} is a pipe: the parent buffers"
        assert hasattr(
            kw[stream], "fileno"
        ), f"{stream} is not a file object: {kw[stream]!r}"


# ---------------------------------------------------------------------------
# The "always return a structured RunResult" contract, at the sites that broke it
# ---------------------------------------------------------------------------
def test_a_gate_parse_failure_cpython_spells_memoryerror_is_a_result_not_a_raise():
    """~20 KB of source raises MemoryError("Parser stack overflowed") inside
    `ast.parse`. It is UNDER SANDBOX_MAX_CODE_BYTES (65536), so tasks.py's size
    cap does not stop it, and `check_code_safe` caught only SyntaxError -- so it
    propagated out of run_code and out of the Celery task.
    """
    r = run_code("x=" + "-" * 20000 + "1", json.dumps({"records": [{}]}), **_DEFAULTS)
    assert r.success is False
    assert "does not parse" in r.error, r.error
    # The TYPE, never the exception text: only SyntaxError.msg is user-safe.
    assert "MemoryError" in r.error, r.error


def test_enospc_while_staging_the_script_is_a_result_not_a_raise():
    """`script.write_text` sits outside the inner try by construction. On the
    256 MB tmpfs this service runs with, ENOSPC is routine -- and once /tmp is
    full EVERY subsequent job on the worker took this path.
    """
    with patch(
        "sandbox.runner.Path.write_text",
        side_effect=OSError(28, "No space left on device"),
    ):
        r = run_code("x = 1\n", json.dumps({"records": [{}]}), **_DEFAULTS)
    assert r.success is False
    assert r.error == "execution failed: OSError", r.error


def test_enospc_opening_the_tempdir_is_a_result_not_a_raise():
    with patch(
        "sandbox.runner.tempfile.TemporaryDirectory",
        side_effect=OSError(28, "No space left on device"),
    ):
        r = run_code("x = 1\n", json.dumps({"records": [{}]}), **_DEFAULTS)
    assert r.success is False
    assert r.error == "execution failed: OSError", r.error


def test_the_child_is_detached_by_start_new_session_not_preexec_fn():
    """`_kill_group` only works because the child is a session leader.

    That used to come from `os.setsid()` inside `preexec_fn`, which runs Python
    bytecode in the forked child -- unsafe in a worker that has threads. If a
    future edit drops this kwarg, the kill path silently degrades to signalling
    the worker's own group, which the `_kill_group` guard then refuses -- so the
    child is never killed and the job reports an ordinary timeout.
    """
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.returncode = 0
    with (
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc) as mock_popen,
        patch("sandbox.runner.os.getpgid", return_value=4321),
        patch("sandbox.runner.os.killpg"),
    ):
        run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}),
            **_DEFAULTS,
        )
    assert mock_popen.call_args.kwargs.get("start_new_session") is True


def test_kill_group_refuses_to_signal_its_own_process_group():
    """The guard that stops a timeout from SIGKILLing the worker and every
    sibling job. Reachable in production: if session creation fails the child
    stays in the parent's group, and `os.getpgid(child)` then returns the
    worker's own pgid.

    Previously uncovered -- deleting `or pgid == os.getpgrp()` left the suite
    green.
    """
    from sandbox.runner import _kill_group

    with patch("sandbox.runner.os.killpg") as killpg:
        _kill_group(None, "x")
        _kill_group(1, "x")
        _kill_group(os.getpgrp(), "x")
        assert killpg.call_count == 0, "signalled a group it must refuse"
        # and it does signal an ordinary foreign group
        _kill_group(4321, "x")
        assert killpg.call_count == 1


def test_a_failed_pgid_read_is_logged_because_the_kill_becomes_a_no_op(caplog):
    """The log IS the fix, so it needs a guard.

    `_pgid_of` returning None makes `_kill_group` a no-op while the result
    still says the job timed out, so a runaway child survives with the log as
    the only trace. Reverting `_pgid_of` to a silent `except` left the whole
    suite green, which is why this exists.
    """
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.wait.side_effect = [subprocess.TimeoutExpired("x", 2), 0]
    with (
        patch("sandbox.runner.os.getpgid", side_effect=ProcessLookupError),
        patch("sandbox.runner.subprocess.Popen", return_value=mock_proc),
        patch("sandbox.runner.os.killpg") as mock_killpg,
        caplog.at_level("WARNING"),
    ):
        r = run_code("while True:\n    pass\n", "{}", **{**_DEFAULTS, "timeout": 2})
    assert r.success is False
    assert "a timeout kill would be a no-op" in caplog.text
    # The whole point: no kill was attempted, and the log is what says so.
    assert mock_killpg.call_count == 0


def test_an_oversized_valid_utf8_file_is_refused_as_too_big_not_as_bad_encoding(tmp_path):
    """Pins the FILE check, which the payload check would otherwise mask.

    Both checks refuse an oversized file, so removing the file check leaves the
    suite green on the outcome alone. They differ in the message, and for a
    perfectly valid UTF-8 file the payload check's message ("not valid UTF-8")
    would be a lie. Asserting the message is what distinguishes them.

    The file check also bounds the READ, so the parent's peak memory does not
    scale with an operator knob — a property no assertion here can reach, and
    the reason the check is not redundant.
    """
    from sandbox.runner import _result_from_output

    out = tmp_path / "output.jsonl"
    out.write_text('{"k": "' + "a" * 4000 + '"}\n')  # valid UTF-8, over the cap
    r = _result_from_output(out, max_output_bytes=512, max_rows=100, stdout="", stderr="")
    assert r.success is False
    assert r.error == "execution failed: output exceeds size cap", r.error
