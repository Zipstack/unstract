import json
import os
from unittest import mock

import pytest
from sandbox import tasks

_ECHO = (
    "import json, sys\n"
    "d = json.load(open(sys.argv[1]))\n"
    "open(sys.argv[2],'w').write(json.dumps({'n2': d['records'][0]['n']*2})+'\\n')\n"
)


def _call(**over):
    payload = {
        "request_id": "req-1",
        "code": _ECHO,
        "input_json": json.dumps({"records": [{"n": 3}]}),
        "timeout": 5,
    }
    payload.update(over)
    return tasks._execute_sandboxed_code_impl(**payload)


def test_happy_path_returns_rows():
    out = _call()
    assert out["success"] is True
    assert out["request_id"] == "req-1"
    assert json.loads(out["rows_jsonl"].strip()) == {"n2": 6}


def test_oversized_code_rejected_before_run():
    out = _call(code="x = 1\n" * 100_000)  # > 64 KiB
    assert out["success"] is False
    assert "code" in out["error"].lower()


def test_oversized_input_rejected():
    out = _call(input_json='{"pad":"' + "a" * 2_000_000 + '"}')
    assert out["success"] is False
    assert "input" in out["error"].lower()


@mock.patch.dict(os.environ, {"SANDBOX_TIMEOUT_MAX": "5"})
def test_timeout_clamped_to_server_max():
    # Caller asks for 999s; server clamps to SANDBOX_TIMEOUT_MAX.
    with mock.patch.object(tasks, "run_code") as m:
        m.return_value = tasks.RunResult(success=True, rows_jsonl="", rows_written=0)
        _call(timeout=999)
        assert m.call_args.kwargs["timeout"] == 5


def test_non_numeric_timeout_degrades_to_structured_failure():
    # int(timeout) must never raise out of the task -- a non-numeric timeout
    # degrades to a structured _fail() like every other bad-input path.
    out = _call(timeout="not-a-number")
    assert out["success"] is False
    assert "timeout" in out["error"].lower()


def test_none_code_degrades_to_structured_failure():
    # code.encode() on a None/non-str code must not raise AttributeError.
    out = _call(code=None)
    assert out["success"] is False
    assert "code" in out["error"].lower()


def test_none_input_json_degrades_to_structured_failure():
    out = _call(input_json=None)
    assert out["success"] is False
    assert "input_json" in out["error"].lower()


class TestIntEnvGuards:
    """`_int_env`'s two guards, each pinned by the value that reaches `run_code`.

    These exist because both guards survived mutation: replacing the floor
    with `if False:` and replacing the parse handler with a dead
    `except KeyboardInterrupt` each left the whole sandbox suite green. The
    floor is the one that matters most -- `resource.RLIM_INFINITY == -1`, so an
    unguarded `-1` turns a containment cap OFF.

    Each asserts the kwarg actually passed to `run_code`, not the log line,
    because the log is not what the child is launched with.
    """

    def _memory_mb_passed_to_run_code(self):
        with mock.patch.object(tasks, "run_code") as m:
            m.return_value = tasks.RunResult(success=True)
            _call()
            return m.call_args.kwargs

    @mock.patch.dict(os.environ, {"SANDBOX_MAX_PIDS": "-1"})
    def test_a_negative_cap_is_clamped_to_the_floor_not_passed_through(self):
        # -1 is RLIM_INFINITY. Passing it through would remove the cap, which
        # is the single failure mode a limit must not have.
        kwargs = self._memory_mb_passed_to_run_code()
        assert kwargs["max_pids"] == 1

    @mock.patch.dict(os.environ, {"SANDBOX_MEMORY_MB": "0"})
    def test_a_zero_cap_is_clamped_to_the_floor(self):
        # 64, not 1. This expectation was deliberately raised: every cap used to
        # share `minimum=1`, which is legal for all eight and USABLE for none of
        # the memory/byte ones. A clamp to 1 cleared the floor silently and gave
        # the child a 1 MiB RLIMIT_AS, so the interpreter died on SIGSEGV with
        # empty stdout AND stderr and the caller was told its own code failed.
        # 64 is measured as the lowest value that completes the workload the
        # codegen prompt produces -- see the floors in `tasks.py`.
        kwargs = self._memory_mb_passed_to_run_code()
        assert kwargs["memory_mb"] == 64

    @mock.patch.dict(os.environ, {"SANDBOX_MEMORY_MB": "0"})
    def test_clamping_to_the_floor_is_loud(self, caplog):
        # The clamp is the operator's only signal that the value they set was
        # unusable. Deleting the warning left the suite green before this.
        with caplog.at_level("WARNING"):
            self._memory_mb_passed_to_run_code()
        assert "SANDBOX_MEMORY_MB" in caplog.text
        assert "clamping" in caplog.text.lower()

    @mock.patch.dict(os.environ, {"SANDBOX_MEMORY_MB": "256m"})
    def test_a_malformed_cap_falls_back_to_the_default_loudly(self):
        kwargs = self._memory_mb_passed_to_run_code()
        assert kwargs["memory_mb"] == 512

    @mock.patch.dict(os.environ, {"SANDBOX_MEMORY_MB": ""})
    def test_a_blank_cap_is_treated_as_unset_and_warns_about_nothing(self, caplog):
        # Compose's `- KEY=${KEY:-}` form sets the empty string rather than
        # omitting the variable, and the e2e compose uses it for all eight
        # caps -- so a blank must be the quiet path, or the warning fires on
        # every healthy job and stops meaning anything.
        with caplog.at_level("WARNING"):
            kwargs = self._memory_mb_passed_to_run_code()
        assert kwargs["memory_mb"] == 512
        assert "SANDBOX_MEMORY_MB" not in caplog.text

    @mock.patch.dict(os.environ, {"SANDBOX_MEMORY_MB": "512m"})
    def test_a_malformed_cap_does_still_warn(self, caplog):
        # The other half of the blank-is-quiet change: a genuine typo must
        # remain loud, or the fix above would have bought silence everywhere.
        with caplog.at_level("WARNING"):
            self._memory_mb_passed_to_run_code()
        assert "SANDBOX_MEMORY_MB" in caplog.text


def test_the_configured_caps_are_logged_once_per_process(caplog):
    """`_CAPS_LOGGED` guards the one line an operator needs.

    Both directions survived mutation before this test: deleting the guard made
    the dump fire once per job (the noise the docstring says it exists to
    avoid), and stubbing the body made it fire never (losing the only signal
    that distinguishes a Helm value that rendered to nothing from a deployment
    that never configured caps).
    """
    tasks._CAPS_LOGGED = False
    try:
        with mock.patch.object(tasks, "run_code") as m, caplog.at_level("INFO"):
            m.return_value = tasks.RunResult(success=True)
            _call()
            _call()
        assert caplog.text.count("configured caps") == 1, caplog.text
    finally:
        tasks._CAPS_LOGGED = False


@pytest.mark.parametrize(
    "label,kwargs",
    [
        # `len(x.encode())` raises UnicodeEncodeError on a lone surrogate, and
        # `json.loads('"\\udcff"')` produces one without complaint -- so both
        # LLM-generated code and document-derived input can carry it.
        ("lone surrogate in code", {"code": "x = 1  # \udcff"}),
        ("lone surrogate in input_json", {"input_json": '{"k": "\udcff"}'}),
        # `int(inf)` raises OverflowError, which the named numeric guard does
        # NOT catch. `json.loads("1e400")` is strictly valid JSON and yields inf,
        # so any producer can emit it.
        ("infinite timeout", {"timeout": float("inf")}),
    ],
)
def test_inputs_that_raise_outside_the_named_guards_still_return_a_result(label, kwargs):
    """No input may RAISE out of the task; every one degrades to a result dict.

    Raising is strictly worse than returning a failure here: the task does not
    raise to signal retry, so an exception reaches the PG consumer, which
    redelivers to `max_attempts` -- re-running the same doomed payload each time
    -- and then poison-parks it with "exceeded max_attempts" instead of a
    message naming the actual problem.

    These three inputs are the ones that escaped the per-site guards. The guard
    is the wrapper in `_execute_sandboxed_code_impl`, not three more
    except-clauses, so this test pins the wrapper: it fails if the wrapper is
    removed, whatever new site a later edit adds.
    """
    out = _call(**kwargs)
    assert out["success"] is False, label
    assert out["error"].startswith("invalid request: "), (label, out["error"])
    assert out["rows_written"] == 0


def test_the_named_guards_still_give_their_specific_reason():
    """The wrapper must not swallow the cases that already had a good message.

    A bare `except Exception` around the body would make every bad input report
    `invalid request: <TypeError>`, which is a regression in diagnosis even
    though the shape is right. The named guards run first and keep their text.
    """
    assert "timeout" in _call(timeout="not-a-number")["error"].lower()
    assert "string" in _call(code=None)["error"].lower()


def test_zero_timeout_clamps_to_the_floor_not_the_ceiling():
    """0 must not select the server MAXIMUM.

    `if timeout` sent 0 down the absent branch and returned `timeout_max`, the
    loosest value available, while -5 clamped to 1 -- two adjacent nonsense
    values resolving to opposite extremes, silently. 0 reads as
    none/immediate/unset, never as "give me the ceiling".
    """
    with mock.patch.dict(os.environ, {"SANDBOX_TIMEOUT_MAX": "60"}):
        with mock.patch.object(tasks, "run_code") as m:
            m.return_value = tasks.RunResult(success=True)
            _call(timeout=0)
            assert m.call_args.kwargs["timeout"] == 1


def test_absent_timeout_still_takes_the_server_ceiling():
    """The documented advisory default survives the fix above."""
    with mock.patch.dict(os.environ, {"SANDBOX_TIMEOUT_MAX": "60"}):
        with mock.patch.object(tasks, "run_code") as m:
            m.return_value = tasks.RunResult(success=True)
            _call(timeout=None)
            assert m.call_args.kwargs["timeout"] == 60
