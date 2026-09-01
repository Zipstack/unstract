"""Sandbox worker task: run one generated-code request, return the result.

Task name ``execute_sandboxed_code`` is routed to the ``sandbox_codegen``
queue (registry.py). All caps are re-clamped server-side here — the caller's
values are advisory only.
"""
import logging
import os

from queue_backend import worker_task
from sandbox.runner import RunResult, run_code

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _execute_sandboxed_code_impl(
    request_id: str, code: str, input_json: str, timeout: int
) -> dict:
    max_code = _int_env("SANDBOX_MAX_CODE_BYTES", 65536)
    max_input = _int_env("SANDBOX_MAX_INPUT_BYTES", 1_048_576)
    max_output = _int_env("SANDBOX_MAX_OUTPUT_BYTES", 1_048_576)
    max_rows = _int_env("SANDBOX_MAX_ROWS", 100_000)
    timeout_max = _int_env("SANDBOX_TIMEOUT_MAX", 60)
    grace = _int_env("SANDBOX_TIMEOUT_GRACE", 5)
    memory_mb = _int_env("SANDBOX_MEMORY_MB", 512)
    max_pids = _int_env("SANDBOX_MAX_PIDS", 16)

    if len(code.encode()) > max_code:
        return _fail(request_id, "code exceeds size cap")
    if len(input_json.encode()) > max_input:
        return _fail(request_id, "input exceeds size cap")

    eff_timeout = max(1, min(int(timeout) if timeout else timeout_max, timeout_max))
    r: RunResult = run_code(
        code, input_json,
        timeout=eff_timeout, max_output_bytes=max_output, max_rows=max_rows,
        memory_mb=memory_mb, max_pids=max_pids, grace=grace,
    )
    return {
        "request_id": request_id,
        "success": r.success,
        "rows_jsonl": r.rows_jsonl,
        "rows_written": r.rows_written,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "error": r.error,
    }


def _fail(request_id: str, msg: str) -> dict:
    return {
        "request_id": request_id, "success": False, "rows_jsonl": "",
        "rows_written": 0, "stdout": "", "stderr": "", "error": msg,
    }


@worker_task(name="execute_sandboxed_code")
def execute_sandboxed_code(request_id, code, input_json, timeout):
    return _execute_sandboxed_code_impl(request_id, code, input_json, timeout)
