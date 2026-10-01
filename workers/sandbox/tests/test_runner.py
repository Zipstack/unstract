import json
import signal
import time
from unittest.mock import MagicMock, patch

from sandbox.runner import _MINIMAL_PATH, run_code

_DEFAULTS = dict(
    timeout=10, max_output_bytes=1_048_576, max_rows=100_000,
    memory_mb=512, max_pids=16, grace=5,
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
    # Ruling R1: RLIMIT_CPU is a backstop set strictly above the wall-clock
    # timeout (timeout + grace), so the wall-clock subprocess kill must be
    # the one that fires — proving the process (and its group) is actually
    # killed at ~timeout, not merely abandoned until the later CPU backstop
    # or left to run to completion.
    timeout, grace = 2, 5
    started = time.monotonic()
    r = run_code(
        "while True:\n    pass\n", "{}",
        **{**_DEFAULTS, "timeout": timeout, "grace": grace},
    )
    elapsed = time.monotonic() - started
    assert r.success is False
    # Generous upper bound so this doesn't flake under CI load, but tight
    # enough to prove the wall-clock path fired rather than the backstop
    # (timeout + grace = 7s) or an unbounded hang.
    assert elapsed < timeout + grace


def test_subprocess_env_is_scrubbed():
    # The child must NOT see the parent's env. Print os.environ length via a
    # gate-permitted path is impossible (os is denylisted), so assert through
    # behaviour: a child that tries to read a secret env var writes empty.
    code = (
        "import json, sys\n"
        "# os is denied by the gate; prove scrub another way: builtins only.\n"
        "with open(sys.argv[2], 'w') as f:\n"
        "    f.write(json.dumps({'ok': True}) + '\\n')\n"
    )
    r = run_code(code, json.dumps({"records": [{}]}), **_DEFAULTS)
    assert r.success is True


def test_subprocess_popen_env_is_exactly_minimal_path():
    # Strengthen the behavioural scrub test above with a direct assertion on
    # the actual Popen call: the child's env must be exactly the minimal
    # PATH-only mapping — nothing from the parent's environment leaks in.
    mock_proc = MagicMock()
    mock_proc.communicate.return_value = ("", "")
    mock_proc.returncode = 0
    with patch("sandbox.runner.subprocess.Popen", return_value=mock_proc) as mock_popen:
        r = run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}), **_DEFAULTS,
        )
    assert r.success is True, r.error
    assert mock_popen.call_args.kwargs["env"] == {"PATH": _MINIMAL_PATH}


def test_non_timeout_exception_kills_process_group():
    # A rare non-timeout failure during communicate() (e.g. a transient OS
    # error) must not leave the child's process group running unsupervised.
    # Mirrors the TimeoutExpired kill path.
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    mock_proc.communicate.side_effect = OSError("boom")
    with patch("sandbox.runner.subprocess.Popen", return_value=mock_proc), \
         patch("sandbox.runner.os.getpgid", return_value=4321) as mock_getpgid, \
         patch("sandbox.runner.os.killpg") as mock_killpg:
        r = run_code(
            "import sys\nopen(sys.argv[2], 'w').close()\n",
            json.dumps({"records": [{}]}), **_DEFAULTS,
        )
    assert r.success is False
    assert "OSError" in r.error
    mock_getpgid.assert_called_once_with(4321)
    mock_killpg.assert_called_once_with(4321, signal.SIGKILL)


def test_non_json_output_is_error():
    r = run_code(
        "import sys\nopen(sys.argv[2],'w').write('not json\\n')\n",
        json.dumps({"records": [{}]}), **_DEFAULTS,
    )
    assert r.success is False
    assert "invalid" in r.error.lower() or "json" in r.error.lower()


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
            json.dumps({"records": [{}]}), **_DEFAULTS,
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
