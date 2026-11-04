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


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """Read a positive integer cap from the environment, LOUDLY on refusal.

    Two silent degradations used to live here, both of them on the containment
    controls `gate.py` names as the real security boundary.

    A parse failure (`SANDBOX_MEMORY_MB=512m`, `SANDBOX_MAX_ROWS=1e5`, an empty
    value) returned the built-in default with nothing said, so an operator's
    tightening was discarded invisibly.

    Worse, nothing applied a floor. `resource.RLIM_INFINITY == -1`, so
    `SANDBOX_MAX_PIDS=-1` and `SANDBOX_MAX_OUTPUT_BYTES=-1` reached
    `setrlimit(..., (-1, -1))` and made the cap UNLIMITED -- a typo turning a
    limit off is the one failure mode a limit must not have.

    Validation belongs here, in the parent: `_limits()` runs in `preexec_fn`,
    post-fork in the child, where there is nowhere for a log to go.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "sandbox: %s=%r is not an integer; using the default %d", name, raw, default
        )
        return default
    if value < minimum:
        logger.warning(
            "sandbox: %s=%d is below the minimum %d; using the default %d "
            "(a non-positive rlimit reads as RLIM_INFINITY -- i.e. no cap)",
            name,
            value,
            minimum,
            default,
        )
        return default
    return value


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

    # A None/non-str code or input_json (or a non-numeric timeout) must
    # degrade to a structured failure like every other bad-input path here,
    # not raise (AttributeError on `.encode()`, ValueError/TypeError on
    # `int()`) out of a task that's supposed to always return a result dict.
    if not isinstance(code, str):
        return _fail(request_id, "code must be a string")
    if not isinstance(input_json, str):
        return _fail(request_id, "input_json must be a string")
    if len(code.encode()) > max_code:
        return _fail(request_id, "code exceeds size cap")
    if len(input_json.encode()) > max_input:
        return _fail(request_id, "input exceeds size cap")

    try:
        eff_timeout = max(1, min(int(timeout) if timeout else timeout_max, timeout_max))
    except (TypeError, ValueError):
        return _fail(request_id, "timeout must be numeric")
    r: RunResult = run_code(
        code,
        input_json,
        timeout=eff_timeout,
        max_output_bytes=max_output,
        max_rows=max_rows,
        memory_mb=memory_mb,
        max_pids=max_pids,
        grace=grace,
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
        "request_id": request_id,
        "success": False,
        "rows_jsonl": "",
        "rows_written": 0,
        "stdout": "",
        "stderr": "",
        "error": msg,
    }


@worker_task(name="execute_sandboxed_code")
def execute_sandboxed_code(request_id, code, input_json, timeout):
    return _execute_sandboxed_code_impl(request_id, code, input_json, timeout)
