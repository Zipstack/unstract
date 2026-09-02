import json
import os
from unittest import mock

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
