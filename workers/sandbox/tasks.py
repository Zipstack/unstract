"""Sandbox worker task: run one generated-code request, return the result.

Task name ``execute_sandboxed_code`` is routed to the ``sandbox_codegen``
queue (registry.py). All caps are re-clamped server-side here — the caller's
values are advisory only.
"""

import logging
import os

from queue_backend import worker_task
from sandbox.runner import RunResult, run_code

#: Per-job address-space ceiling when `SANDBOX_MEMORY_MB` is unset, in MiB.
#: It becomes `RLIMIT_AS` on each child.
#:
#: NAMED rather than inline so the deployment surfaces can read it instead of
#: restating it. `workers/tests/test_queue_consumer_wiring.py` checks that the
#: dev compose sandbox's `mem_limit` covers tmpfs + this x lanes + parent
#: headroom, and it hard-coded 512 -- so raising this default here would have
#: left that budget arithmetic quietly checking the wrong number, which is the
#: one thing that test exists to prevent. Reported as a Low on #2309.
DEFAULT_SANDBOX_MEMORY_MB = 512

logger = logging.getLogger(__name__)

# Celery's trace logger logs a task's RETURN VALUE at INFO ("Task ... succeeded
# in Ns: <retval>"). This task returns `rows_jsonl`, `stdout` and `stderr` --
# document-derived customer data -- so leaving it at INFO copies extracted rows
# into the worker log, outside the job's own access and retention controls. The
# PG consumer runs the body through `task.apply`, which fires the same signals,
# so both transports are affected.
#
# Same line, same reason, as `workers/executor/tasks.py`. Found by a review bot:
# this sink is the framework's, not ours, so a sweep that traces `logger.*` calls
# in this package does not see it.
logging.getLogger("celery.app.trace").setLevel(logging.WARNING)


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    """Read a positive integer cap from the environment, LOUDLY on refusal.

    Two silent degradations used to live here, both of them on the containment
    controls `gate.py` names as the real security boundary.

    A parse failure (`SANDBOX_MEMORY_MB=512m`, `SANDBOX_MAX_ROWS=1e5`) returned
    the built-in default with nothing said, so an operator's tightening was
    discarded invisibly. A BLANK value is deliberately NOT in that list: it is
    treated as unset and stays silent, per the three dispositions below.

    Worse, nothing applied a floor. `resource.RLIM_INFINITY == -1`, so
    `SANDBOX_MAX_PIDS=-1` and `SANDBOX_MAX_OUTPUT_BYTES=-1` reached
    `setrlimit(..., (-1, -1))` and made the cap UNLIMITED -- a typo turning a
    limit off is the one failure mode a limit must not have.

    Validation belongs here, in the parent: `_limits()` runs in `preexec_fn`,
    post-fork in the child, where there is nowhere for a log to go. Note this
    validates the SHAPE of the requested number, a different failure from the
    kernel REFUSING it -- a value that passes here cleanly is exactly the one
    `_apply` discards if it exceeds a hard limit.

    Three dispositions, and they differ:

    - **unset or blank** -> the built-in default, silently. A blank is the
      same operator intent as unset, and warning on it made the healthy path
      noisy enough to drown the two cases below.
    - **unparseable** (`512m`, `1e5`) -> the built-in default, loudly. There
      is no numeric intent to clamp toward, so the default is the only option;
      note this means a unit-suffix typo made while TIGHTENING still lands on
      a default that may be looser than intended. That is a known limit of
      this function, not something it fixes.
    - **below the floor** -> `minimum`, loudly. Here there IS numeric intent
      and it is unusable, so clamping beats substituting a value the operator
      never chose.

    `_log_configured_caps` is what gives an operator the one thing none of the
    above does: the caps a job actually ran with.
    """
    raw = os.environ.get(name)
    # `not raw.strip()` and not just `raw is None`: see the blank-value note
    # above. An unset variable and `KEY=` are the same operator intent.
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "sandbox: %s=%r is not an integer; using the default %d", name, raw, default
        )
        return default
    if value < minimum:
        # No rlimit semantics in this message: only four of the eight caps
        # become rlimits, and for the others a negative value is the TIGHTEST
        # setting rather than no cap at all (`SANDBOX_MAX_ROWS=-1` trips on the
        # first row). The per-name mechanism is in the docstring above.
        logger.warning(
            "sandbox: %s=%d is below the minimum %d; clamping to %d "
            "(clamping to the floor rather than back to the default %d, which "
            "can be looser than what you asked for)",
            name,
            value,
            minimum,
            minimum,
            default,
        )
        return minimum
    return value


#: Guard so the cap dump below fires once per worker process, not once per job.
_CAPS_LOGGED = False


def _log_configured_caps(caps: dict[str, int]) -> None:
    """Log the caps this process was CONFIGURED with, once.

    "Configured", not "effective": these are `_int_env`'s return values -- what
    the parent decided -- and nothing here reads back what the kernel accepted.
    THREE of the eight become rlimits directly in `_limits._apply`:
    `SANDBOX_MAX_OUTPUT_BYTES` -> `RLIMIT_FSIZE`, `SANDBOX_MEMORY_MB` ->
    `RLIMIT_AS`, `SANDBOX_MAX_PIDS` -> `RLIMIT_NPROC`. A failed `setrlimit` is
    swallowed per limit, so a cap named here can be absent in the child.

    `_apply` sets five rlimits in all, and the other two are not in this dump
    for different reasons. `RLIMIT_CPU` IS env-derived -- `runner` computes it
    as `max(timeout + grace, timeout + 1)`, i.e. from `SANDBOX_TIMEOUT_GRACE`
    and a timeout already clamped by `SANDBOX_TIMEOUT_MAX` -- so it is omitted
    as a derived value rather than a fixed one, and an operator should know
    that `SANDBOX_TIMEOUT_GRACE` sets a kernel CPU limit. Only `RLIMIT_NOFILE`
    is genuinely not env-derived: it is hard-coded to 64.

    The one thing `_int_env`'s per-call warnings cannot tell an operator is
    what the caps ENDED UP as -- an unset variable and a blank one are both
    silent by design, so a Helm value that rendered to nothing is otherwise
    indistinguishable from a deployment that never configured caps. Logged
    once at the first job rather than per job, because eight lines per
    execution is what made the previous warning useless.
    """
    global _CAPS_LOGGED
    if _CAPS_LOGGED:
        return
    _CAPS_LOGGED = True
    logger.info(
        "sandbox: configured caps %s",
        ", ".join(f"{k}={v}" for k, v in sorted(caps.items())),
    )


def _execute_sandboxed_code_impl(
    request_id: str, code: str, input_json: str, timeout: int
) -> dict:
    r"""Always return a result dict, never raise.

    The guard is here rather than at each site that can fail, for the reason
    `runner.run_code`'s own wrapper gives: guarding each site individually is a
    rule a future edit has to remember, and three sites had already forgotten
    it. Measured before this wrapper existed:

    - `len(code.encode())` raised `UnicodeEncodeError` on a lone surrogate, and
      `json.loads('"x = 1 # \\udcff"')` yields one without complaint, so
      LLM-generated text could carry it.
    - the same on `input_json`, which is document-derived.
    - `int(timeout)` raised `OverflowError` on `inf`, which the numeric handler
      below does not catch; `json.loads("1e400")` is valid JSON and yields it.

    Raising out of the task is worse than returning a failure: the PG consumer
    redelivers to `max_attempts`, re-running the same doomed payload each time,
    and then poison-parks it with "exceeded max_attempts" instead of the
    specific message the guards below were written to produce.

    The named guards are kept rather than replaced -- they give the caller an
    actionable reason, and this only stops the unnamed ones escaping.
    """
    try:
        return _execute_sandboxed_code_unguarded(request_id, code, input_json, timeout)
    except Exception as exc:
        logger.warning(
            "sandbox: request %s failed outside the guarded region: %s",
            request_id,
            exc,
            exc_info=True,
        )
        return _fail(request_id, f"invalid request: {type(exc).__name__}")


def _execute_sandboxed_code_unguarded(
    request_id: str, code: str, input_json: str, timeout: int
) -> dict:
    # Each cap passes its OWN floor. `minimum=1` is legal for all eight and
    # usable for none of the byte/memory ones, and a value that clears the floor
    # is silent -- so the floors below are what make a unit slip loud instead of
    # fatal. Measured, one child per value: SANDBOX_MEMORY_MB=1 becomes
    # RLIMIT_AS=1MiB and the interpreter dies on SIGSEGV (rc -11) with EMPTY
    # stdout AND stderr; =8 dies loading libc ("failed to map segment");
    # =32 runs. SANDBOX_MAX_OUTPUT_BYTES=1 becomes RLIMIT_FSIZE=1 and the child
    # is killed on its first write -- including the write of its own error --
    # giving `exit 120` with stdout 'h' and stderr 'E'. Both are configuration
    # faults reported to the caller as the generated code's fault.
    #
    # The byte floors are a payload's worth, not a kernel minimum: below 4 KiB
    # the cap rejects every realistic script or document, which is an outage
    # rather than a tightening.
    #
    # The 64 MiB memory floor is measured against the workload the codegen
    # prompt actually produces -- `import json, sys`, read `argv[1]`, write
    # `argv[2]` -- not against a bare interpreter: 16 and 24 MiB fail to exec
    # at all (rc 127, libc cannot map), 32 and 48 start and then die (rc 1),
    # and 64 is the first value that completes. A bare `print()` survives on
    # 32, which is why the floor is set from the real workload instead.
    max_code = _int_env("SANDBOX_MAX_CODE_BYTES", 65536, minimum=4096)
    max_input = _int_env("SANDBOX_MAX_INPUT_BYTES", 1_048_576, minimum=4096)
    max_output = _int_env("SANDBOX_MAX_OUTPUT_BYTES", 1_048_576, minimum=4096)
    max_rows = _int_env("SANDBOX_MAX_ROWS", 100_000, minimum=1)
    timeout_max = _int_env("SANDBOX_TIMEOUT_MAX", 60, minimum=1)
    grace = _int_env("SANDBOX_TIMEOUT_GRACE", 5, minimum=1)
    memory_mb = _int_env("SANDBOX_MEMORY_MB", DEFAULT_SANDBOX_MEMORY_MB, minimum=64)
    max_pids = _int_env("SANDBOX_MAX_PIDS", 16, minimum=1)
    _log_configured_caps(
        {
            "SANDBOX_MAX_CODE_BYTES": max_code,
            "SANDBOX_MAX_INPUT_BYTES": max_input,
            "SANDBOX_MAX_OUTPUT_BYTES": max_output,
            "SANDBOX_MAX_ROWS": max_rows,
            "SANDBOX_TIMEOUT_MAX": timeout_max,
            "SANDBOX_TIMEOUT_GRACE": grace,
            "SANDBOX_MEMORY_MB": memory_mb,
            "SANDBOX_MAX_PIDS": max_pids,
        }
    )

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
        # `is None` rather than falsiness. `if timeout` sent 0 down the
        # "absent" branch and handed it `timeout_max` -- the LOOSEST value
        # available -- while -5 clamped to 1, so two adjacent nonsense values
        # resolved to opposite extremes and neither said anything. 0 reads as
        # "none"/"immediate"/"unset" far more naturally than "give me the
        # server ceiling", and every other ambiguous input in this module
        # resolves toward the floor and logs (`_int_env`). Absent still means
        # the ceiling, which is the documented advisory default.
        eff_timeout = (
            timeout_max if timeout is None else max(1, min(int(timeout), timeout_max))
        )
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
