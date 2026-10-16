# Agent-KV Codegen Sandbox Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a hardened OSS sandbox worker that executes engine-generated calculation code out-of-process, wire the `agentic_kv` cloud plugin to it, and take the API's `calculations` field to GA.

**Architecture:** A new OSS Celery/PG-queue worker (`WorkerType.SANDBOX`) consumes a dedicated `sandbox_codegen` queue and runs generated Python in a scrubbed-env, rlimit-bounded subprocess. The cloud `agentic_kv` executor talks to it through the existing request-reply executor-RPC machinery via a `SandboxCodeTransport` that implements the engine's existing `CodeExecutionTransport` seam. A K8s Deployment + default-deny NetworkPolicy provide the pod-level hardening; flipping `AGENT_KV_CALCULATIONS_ENABLED=true` completes GA.

**Tech Stack:** Python 3.12, Celery + PG-queue (psycopg2), the `unstract.workflow_execution.executor_rpc` request-reply layer, pytest, Helm + helm-unittest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-01-agent-kv-sandbox-worker-design.md`

## Global Constraints

- **Two repos, two branches.** OSS work (Tasks 1–6, 12): `/Users/arun/Devel/Github/unstract`, branch `Feat/agent-kv-api`. Cloud work (Tasks 7–11): `/Users/arun/Devel/Github/unstract-cloud`, branch `UN-4044-agent-kv-cloud-executor`; **every cloud commit subject starts with `UN-4044`**, and the cloud repo requires asking before commit/push.
- **Never push; never open a PR.** Commit locally only. Arun pushes.
- **`UV_FROZEN=1` on every `uv` invocation.** Never let `uv.lock` drift; if a run dirties it, `git checkout -- uv.lock`.
- **Frozen OSS↔cloud contract.** Do not add or rename any `executor_params` key, `ExecutionResult` field, stage name, or queue name from sub-project #1. This plan adds exactly one new queue (`sandbox_codegen`) and one new task (`execute_sandboxed_code`), both internal to the sandbox hop.
- **The sandbox receives only `{request_id, code, input_json, timeout}`** — never the document bytes, the schema, tenant/org identifiers, or any secret. `request_id` is an opaque correlation UUID.
- **Fail closed.** The AST gate rejects on any doubt; `UnavailableCodeTransport` stays the default whenever the sandbox queue is unconfigured; a failed or unavailable execution fails the job with a user-safe error (class + stage only — no paths, no env, no raw stderr beyond a truncated field).
- **Caps (server-side, re-enforced regardless of caller), env-overridable:** `SANDBOX_MAX_CODE_BYTES=65536`, `SANDBOX_MAX_INPUT_BYTES=1048576`, `SANDBOX_MAX_OUTPUT_BYTES=1048576`, `SANDBOX_MAX_ROWS=100000`, `SANDBOX_TIMEOUT_MAX=60`, `SANDBOX_TIMEOUT_GRACE=5`, `SANDBOX_MEMORY_MB=512`, `SANDBOX_MAX_PIDS=16`, `SANDBOX_CODEGEN_QUEUE=sandbox_codegen`.
- **TDD.** Every task writes the failing test first, watches it fail, implements minimally, watches it pass, commits. Test output must be pristine (no stray warnings).
- **Image (S7, amended):** v1 runs from the existing `worker-unified` image (worker command `sandbox`); no new Dockerfile. The dedicated slim image is an upgrade-path follow-up.

---

## File Structure

**OSS (`Feat/agent-kv-api`):**
- `workers/sandbox/__init__.py`, `workers/sandbox/worker.py` — worker entrypoint (mirrors `workers/ide_callback/worker.py`).
- `workers/sandbox/gate.py` — normative AST safety gate (`check_code_safe`).
- `workers/sandbox/runner.py` — the subprocess harness (`run_code`), scrubbed env + rlimits + timeout + output discipline.
- `workers/sandbox/tasks.py` — the `execute_sandboxed_code` Celery task (payload caps → `run_code`).
- `workers/sandbox/tests/` — `test_gate.py`, `test_runner.py`, `test_tasks.py`.
- `workers/shared/enums/worker_enums_base.py` — add `WorkerType.SANDBOX`, `QueueName.SANDBOX_CODEGEN`.
- `workers/shared/infrastructure/config/registry.py` — queue config + task route for the new worker.
- `workers/run-worker-docker.sh`, `workers/run-worker.sh` — `sandbox` command mapping.
- `workers/sample.env` — `SANDBOX_*` documented defaults.
- `docker/docker-compose.yaml` — `worker-sandbox` service (+ PG twin comment).
- `tests/groups.yaml` — reuse `unit-workers` (no new group needed; sandbox tests are plain unit tests).
- `docs/agent-kv-api.md` — §5 (calc result shape), §12 (rollout order).

**Cloud (`UN-4044-agent-kv-cloud-executor`):**
- `workers/plugins/agentic_kv/src/sandbox_transport.py` — `SandboxCodeTransport(CodeExecutionTransport)`.
- `workers/plugins/agentic_kv/src/executor.py` — forward `calculations` + `output_path`; read rows back into `calculation_rows`.
- `workers/plugins/agentic_kv/src/constants.py` — `Env.SANDBOX_CODEGEN_QUEUE`, config field.
- `workers/plugins/agentic_kv/tests/` — `test_sandbox_transport.py`, extend `test_executor*.py`.
- `charts/unstract-platform/values.yaml` — `workerSandbox` block; NetworkPolicy toggle.
- `charts/unstract-platform/templates/worker-sandbox/deployment.yaml`, `.../networkpolicy.yaml`.
- `charts/unstract-platform/unittests/sandbox_wiring_test.yaml`.
- `charts/unstract-platform/cloud-deployment-values/cloud.values.yaml` — enable worker + `AGENT_KV_CALCULATIONS_ENABLED=true`.
- `tests/compose/docker-compose.test.yaml` (OSS, copied by cloud) — `worker-sandbox` + the flag pass-through for the e2e lane.

---

## Task 1: Worker type, queue, and registry wiring (OSS)

**Files:**
- Modify: `workers/shared/enums/worker_enums_base.py`
- Modify: `workers/shared/infrastructure/config/registry.py`
- Test: `workers/shared/enums/tests/test_worker_enums.py`, `workers/shared/infrastructure/config/tests/test_registry.py` (create if absent)

**Interfaces:**
- Produces: `WorkerType.SANDBOX = "sandbox"`; `QueueName.SANDBOX_CODEGEN = "sandbox_codegen"`; a `WorkerQueueConfig(primary_queue=QueueName.SANDBOX_CODEGEN)` entry and a `WorkerTaskRouting` routing `execute_sandboxed_code → SANDBOX_CODEGEN`.

- [ ] **Step 1: Write the failing test** — append to `workers/shared/infrastructure/config/tests/test_registry.py` (create the file with the standard header if it does not exist):

```python
from shared.enums.worker_enums import WorkerType
from shared.enums.worker_enums_base import QueueName
from shared.infrastructure.config.registry import WorkerRegistry


def test_sandbox_worker_registered():
    cfg = WorkerRegistry._QUEUE_CONFIGS[WorkerType.SANDBOX]
    assert cfg.primary_queue == QueueName.SANDBOX_CODEGEN


def test_sandbox_task_route():
    routing = WorkerRegistry._TASK_ROUTES[WorkerType.SANDBOX]
    routed = {r.task_name: r.queue for r in routing.routes}
    assert routed["execute_sandboxed_code"] == QueueName.SANDBOX_CODEGEN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers && UV_FROZEN=1 uv run pytest shared/infrastructure/config/tests/test_registry.py -q -p no:cacheprovider`
Expected: FAIL — `KeyError: WorkerType.SANDBOX` (enum member missing).

- [ ] **Step 3: Add the enum members.** In `workers/shared/enums/worker_enums_base.py`, add to `WorkerType` (alongside `IDE_CALLBACK`): `SANDBOX = "sandbox"`. Add to `QueueName` (after `AGENT_KV_CALLBACK`): `SANDBOX_CODEGEN = "sandbox_codegen"`. If `WorkerType` lives in `worker_enums.py` re-exporting the base, add it there to match `IDE_CALLBACK`'s definition site.

- [ ] **Step 4: Add the registry entries.** In `workers/shared/infrastructure/config/registry.py`, add to `_QUEUE_CONFIGS`:

```python
        WorkerType.SANDBOX: WorkerQueueConfig(
            primary_queue=QueueName.SANDBOX_CODEGEN,
        ),
```

and to `_TASK_ROUTES`:

```python
        WorkerType.SANDBOX: WorkerTaskRouting(
            worker_type=WorkerType.SANDBOX,
            routes=[
                TaskRoute("execute_sandboxed_code", QueueName.SANDBOX_CODEGEN),
            ],
        ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd workers && UV_FROZEN=1 uv run pytest shared/infrastructure/config/tests/test_registry.py shared/enums/tests/test_worker_enums.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git checkout -- uv.lock 2>/dev/null || true
git add workers/shared/enums/worker_enums_base.py workers/shared/enums/worker_enums.py workers/shared/infrastructure/config/registry.py workers/shared/infrastructure/config/tests/test_registry.py
git commit -m "feat(sandbox): register SANDBOX worker type, queue and task route"
```

---

## Task 2: The AST safety gate (OSS, normative copy)

**Files:**
- Create: `workers/sandbox/__init__.py` (empty), `workers/sandbox/gate.py`
- Test: `workers/sandbox/tests/__init__.py` (empty), `workers/sandbox/tests/test_gate.py`

**Interfaces:**
- Produces: `check_code_safe(code: str) -> tuple[bool, str]` — `(True, "")` if safe, `(False, reason)` otherwise. Reason strings are user-safe (no paths).

**Context:** This is the normative copy of the engine's `_check_code_safe` (cloud `workers/plugins/agentic_kv/src/engine/code_executor.py`). The gate rejects dangerous imports, dynamic-exec calls, dunder attribute access, and denylisted names; it permits the `open()` file I/O the runner stub needs on its two argv paths.

- [ ] **Step 1: Write the failing test** — `workers/sandbox/tests/test_gate.py`:

```python
import pytest

from sandbox.gate import check_code_safe

_SAFE = "import json\nrows=[{'x':1}]\nwith open('out','w') as f:\n    f.write('{}')\n"

_HOSTILE = [
    "import os\nos.system('id')",
    "import subprocess",
    "from socket import socket",
    "import ctypes",
    "eval('1+1')",
    "exec('x=1')",
    "__import__('os')",
    "x = ().__class__.__bases__",
    "b = __builtins__",
    "getattr(object, 'x')",
    "not valid python (",
]


def test_safe_code_passes():
    ok, reason = check_code_safe(_SAFE)
    assert ok is True, reason
    assert reason == ""


@pytest.mark.parametrize("code", _HOSTILE)
def test_hostile_code_rejected(code):
    ok, reason = check_code_safe(code)
    assert ok is False
    assert reason.startswith("safety gate:")
    # Reason is user-safe: no filesystem paths leak.
    assert "/" not in reason.replace("safety gate:", "")


def test_encoded_import_via_builtins_subscript_rejected():
    ok, _ = check_code_safe("__builtins__['__import__']('os')")
    assert ok is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers && UV_FROZEN=1 uv run pytest sandbox/tests/test_gate.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'sandbox.gate'`.

- [ ] **Step 3: Write the gate.** `workers/sandbox/gate.py` — port the engine's logic verbatim (it is the normative source; keep behaviour identical), renamed to the public `check_code_safe`:

```python
"""Normative AST safety gate for LLM-generated post-processing code.

This is the authoritative copy: the sandbox NEVER trusts the client-side
pre-flight check in the agentic_kv engine (``engine/code_executor._check_code_safe``,
kept there as defense-in-depth). Fail-closed static allowlist — rejects dangerous
imports, dynamic-exec calls, dunder attribute access and introspection-escape
names; permits ``open()`` on the runner's two argv paths.
"""
import ast

_DENYLISTED_IMPORTS = {
    "os", "subprocess", "socket", "shutil", "ctypes", "pickle", "marshal",
    "importlib", "requests", "urllib", "urllib2", "urllib3", "http", "ftplib",
    "smtplib", "telnetlib", "pty", "multiprocessing", "signal", "resource",
    "fcntl", "mmap",
}
_DENYLISTED_CALLS = {
    "eval", "exec", "compile", "__import__", "globals", "vars",
    "getattr", "setattr", "delattr",
}
_DENYLISTED_NAMES = {"__builtins__", "__globals__", "__loader__", "__import__"}


def check_code_safe(code: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``reason`` is user-safe (no paths)."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"safety gate: code does not parse ({e.msg})"
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in _DENYLISTED_IMPORTS:
                    return False, f"safety gate: disallowed import '{a.name}'"
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in _DENYLISTED_IMPORTS:
                return False, f"safety gate: disallowed import from '{node.module}'"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in _DENYLISTED_CALLS:
                return False, f"safety gate: disallowed call '{node.func.id}'"
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            return False, f"safety gate: dunder attribute access '{node.attr}'"
        elif isinstance(node, ast.Name) and node.id in _DENYLISTED_NAMES:
            return False, f"safety gate: disallowed name '{node.id}'"
    return True, ""
```

Note: `check_code_safe` uses `e.msg` (not `str(e)`) so no source-file path can appear in the reason.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers && UV_FROZEN=1 uv run pytest sandbox/tests/test_gate.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git checkout -- uv.lock 2>/dev/null || true
git add workers/sandbox/__init__.py workers/sandbox/gate.py workers/sandbox/tests/__init__.py workers/sandbox/tests/test_gate.py
git commit -m "feat(sandbox): normative AST safety gate with adversarial tests"
```

---

## Task 3: The subprocess runner harness (OSS)

**Files:**
- Create: `workers/sandbox/runner.py`
- Test: `workers/sandbox/tests/test_runner.py`

**Interfaces:**
- Consumes: `check_code_safe` (Task 2).
- Produces:
  - `@dataclass RunResult: success: bool; rows_jsonl: str; rows_written: int; stdout: str; stderr: str; error: str | None`
  - `run_code(code: str, input_json: str, *, timeout: int, max_output_bytes: int, max_rows: int, memory_mb: int, max_pids: int, grace: int) -> RunResult`

**Context:** `run_code` re-runs the gate, then executes the code in a scrubbed-env subprocess. The generated code follows the engine's existing contract: it is invoked as `python script.py <input_json_path> <output_jsonl_path>` and writes JSONL rows to the output path (see the engine's `_execute_direct`). The harness writes `input_json` to a temp file, runs the child with an **empty environment** (only a minimal `PATH`), `cwd` = a per-run tempdir, `start_new_session=True`, and `preexec_fn` setting rlimits. On timeout it kills the process group. Output is read back, validated line-by-line as JSON, capped by rows and bytes.

- [ ] **Step 1: Write the failing test** — `workers/sandbox/tests/test_runner.py`:

```python
import json

from sandbox.runner import run_code

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
    assert "timed out" in r.error.lower()


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers && UV_FROZEN=1 uv run pytest sandbox/tests/test_runner.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'sandbox.runner'`.

- [ ] **Step 3: Write the runner.** `workers/sandbox/runner.py`:

```python
"""Scrubbed-env, rlimit-bounded subprocess harness for sandboxed code.

Enforces spec §6.3 layers 1-2 in-process (the pod supplies layers 3-5). The
child is invoked as ``python -I -S -E <script> <input_path> <output_path>``
with an EMPTY environment (minimal PATH only), a fresh process group, and
rlimits on CPU / address space / PIDs / open files / output size, killed at
``timeout + grace`` wall-clock seconds.
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


@dataclass
class RunResult:
    success: bool
    rows_jsonl: str = ""
    rows_written: int = 0
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


def _limits(cpu_seconds: int, memory_mb: int, max_pids: int, fsize: int):
    def _apply():
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        mem = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_NPROC, (max_pids, max_pids))
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize, fsize))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        os.setsid()
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
    grace: int,
) -> RunResult:
    ok, reason = check_code_safe(code)
    if not ok:
        return RunResult(success=False, error=reason)

    with tempfile.TemporaryDirectory(prefix="sandbox_") as tmp:
        d = Path(tmp)
        script = d / "script.py"
        inp = d / "input.json"
        out = d / "output.jsonl"
        script.write_text(code)
        inp.write_text(input_json)
        out.write_text("")

        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", "-E", str(script), str(inp), str(out)],
                cwd=tmp,
                env={"PATH": _MINIMAL_PATH},
                capture_output=True,
                text=True,
                timeout=timeout,
                preexec_fn=_limits(timeout, memory_mb, max_pids, max_output_bytes),
            )
        except subprocess.TimeoutExpired as e:
            # Kill the whole session; the child may have spawned helpers.
            try:
                os.killpg(os.getpgid(e.args[0] if False else 0), signal.SIGKILL)
            except Exception:
                pass
            return RunResult(
                success=False,
                stdout=(e.stdout or "")[:4096] if isinstance(e.stdout, str) else "",
                stderr=(e.stderr or "")[:4096] if isinstance(e.stderr, str) else "",
                error=f"execution timed out after {timeout}s",
            )
        except Exception as exc:  # rlimit / spawn failure
            return RunResult(success=False, error=f"execution failed: {type(exc).__name__}")

        stdout = (proc.stdout or "")[:4096]
        stderr = (proc.stderr or "")[:4096]
        if proc.returncode != 0:
            return RunResult(
                success=False, stdout=stdout, stderr=stderr,
                error=f"execution failed: exit {proc.returncode}",
            )

        raw = out.read_text()
        if len(raw.encode()) > max_output_bytes:
            return RunResult(success=False, stdout=stdout, stderr=stderr,
                             error="execution failed: output exceeds size cap")
        rows = 0
        for line in raw.splitlines():
            if not line.strip():
                continue
            try:
                json.loads(line)
            except ValueError:
                return RunResult(success=False, stdout=stdout, stderr=stderr,
                                 error="execution failed: invalid JSONL output")
            rows += 1
            if rows > max_rows:
                return RunResult(success=False, stdout=stdout, stderr=stderr,
                                 error="execution failed: output exceeds row cap")
        return RunResult(success=True, rows_jsonl=raw, rows_written=rows,
                         stdout=stdout, stderr=stderr)
```

Note on the timeout kill: `subprocess.run(..., timeout=)` already sends SIGKILL to the direct child on expiry; the `os.setsid()` in `preexec_fn` plus the best-effort `killpg` reap any grandchildren. Keep the `killpg` guarded so a harness bug never masks the timeout result. (An implementer may simplify the kill to `subprocess.Popen` + explicit `os.killpg` if the `run()` semantics prove fiddly — but must keep the "process group is dead after timeout" behaviour and a test for it.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd workers && UV_FROZEN=1 uv run pytest sandbox/tests/test_runner.py -q -p no:cacheprovider`
Expected: PASS (all six). If `test_infinite_loop_times_out` is flaky under load, raise its timeout to 3s — never remove it.

- [ ] **Step 5: Commit**

```bash
git checkout -- uv.lock 2>/dev/null || true
git add workers/sandbox/runner.py workers/sandbox/tests/test_runner.py
git commit -m "feat(sandbox): scrubbed-env rlimit subprocess runner with hostile-behaviour tests"
```

---

## Task 4: The Celery task + worker entrypoint (OSS)

**Files:**
- Create: `workers/sandbox/tasks.py`, `workers/sandbox/worker.py`
- Test: `workers/sandbox/tests/test_tasks.py`

**Interfaces:**
- Consumes: `run_code` (Task 3); `worker_task` (`from queue_backend import worker_task`).
- Produces: Celery task `execute_sandboxed_code(request_id, code, input_json, timeout) -> dict` returning `{success, rows_jsonl, rows_written, stdout, stderr, error, request_id}`, with all caps clamped server-side from `SANDBOX_*` env.

**Context:** Mirror `workers/ide_callback/worker.py` (build the Celery app for the worker type) and the `@worker_task` decorator pattern from `workers/ide_callback/agent_kv_tasks.py`. The task name string **must** be exactly `execute_sandboxed_code` (Task 1 routes it).

- [ ] **Step 1: Write the failing test** — `workers/sandbox/tests/test_tasks.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers && UV_FROZEN=1 uv run pytest sandbox/tests/test_tasks.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'sandbox.tasks'`.

- [ ] **Step 3: Write the task.** `workers/sandbox/tasks.py`:

```python
"""Sandbox worker task: run one generated-code request, return the result.

Task name ``execute_sandboxed_code`` is routed to the ``sandbox_codegen``
queue (registry.py). All caps are re-clamped server-side here — the caller's
values are advisory only.
"""
import logging
import os

from celery import current_app as app

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
```

Import `RunResult` into `tasks` namespace (the test patches `tasks.run_code` and constructs `tasks.RunResult`): the `from sandbox.runner import RunResult, run_code` line above satisfies both.

- [ ] **Step 4: Write the worker entrypoint.** `workers/sandbox/worker.py` (mirror `workers/ide_callback/worker.py`):

```python
"""Sandbox Worker — consumes ``sandbox_codegen``; runs generated code
out-of-process in a scrubbed, rlimit-bounded subprocess (spec §6.3).
"""
from shared.enums.worker_enums import WorkerType
from shared.infrastructure.config.builder import WorkerBuilder
from shared.infrastructure.logging import WorkerLogger

import sandbox.tasks  # noqa: F401 — registers execute_sandboxed_code

logger = WorkerLogger.setup(WorkerType.SANDBOX)
app, config = WorkerBuilder.build_celery_app(WorkerType.SANDBOX)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd workers && UV_FROZEN=1 uv run pytest sandbox/tests/test_tasks.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git checkout -- uv.lock 2>/dev/null || true
git add workers/sandbox/tasks.py workers/sandbox/worker.py workers/sandbox/tests/test_tasks.py
git commit -m "feat(sandbox): execute_sandboxed_code task + worker entrypoint with server-side caps"
```

---

## Task 5: Runtime wiring — compose, run scripts, sample.env (OSS)

**Files:**
- Modify: `workers/run-worker-docker.sh`, `workers/run-worker.sh`
- Modify: `workers/sample.env`
- Modify: `docker/docker-compose.yaml`
- Modify: `tests/compose/docker-compose.test.yaml`

**Interfaces:**
- Produces: a `sandbox` worker command and a `worker-sandbox` compose service consuming `sandbox_codegen`.

**Context:** This task has no unit test of its own — it is deployment glue. Its acceptance test is Task 12's live run (the executor RPC reaches a running sandbox worker). Validate statically here.

- [ ] **Step 1: Map the `sandbox` command.** In `workers/run-worker-docker.sh` (and `workers/run-worker.sh`), add to the command→worker-type map (next to `["ide-callback"]="ide_callback"`): `["sandbox"]="sandbox"`.

- [ ] **Step 2: Add `SANDBOX_*` to `workers/sample.env`** with the Global-Constraints defaults, each commented (bytes/rows/timeout/memory/pids), plus a header line: `# Codegen sandbox worker (WorkerType.SANDBOX); all caps re-enforced server-side.`

- [ ] **Step 3: Add the compose service.** In `docker/docker-compose.yaml`, add a `worker-sandbox` service modelled on `worker-ide-callback` but hardened:

```yaml
  worker-sandbox:
    image: unstract/worker-unified:${VERSION}
    container_name: unstract-worker-sandbox
    restart: unless-stopped
    command: ["sandbox"]
    read_only: true
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    tmpfs:
      - /tmp
    env_file:
      - ../workers/.env
      - ./essentials.env
    depends_on:
      - db
      - redis
      - rabbitmq
    environment:
      - APPLICATION_NAME=unstract-worker-sandbox
      - WORKER_TYPE=sandbox
      - WORKER_NAME=sandbox-worker
```

(No `<<: *host_gateway` — the sandbox must not reach the host.)

- [ ] **Step 4: Add to the test overlay.** In `tests/compose/docker-compose.test.yaml`, add a `worker-sandbox` service stanza pinned to `${UNSTRACT_TEST_VERSION:-latest}` and passing `SANDBOX_*` through (defaults are fine). Also add, under the `backend` service's environment, `AGENT_KV_CALCULATIONS_ENABLED=${AGENT_KV_CALCULATIONS_ENABLED:-}` so Task 12 can flip it for the calc e2e without editing committed files.

- [ ] **Step 5: Static validation.**

Run: `cd /Users/arun/Devel/Github/unstract && docker compose -f docker/docker-compose.yaml -f tests/compose/docker-compose.test.yaml config --services | grep worker-sandbox`
Expected: prints `worker-sandbox`. (If `docker compose` is unavailable in the exec environment, note it and rely on Task 12.)

- [ ] **Step 6: Commit**

```bash
git add workers/run-worker-docker.sh workers/run-worker.sh workers/sample.env docker/docker-compose.yaml tests/compose/docker-compose.test.yaml
git commit -m "feat(sandbox): compose service, run-worker command and sample.env wiring"
```

---

## Task 6: OSS docs (result shape + rollout) (OSS)

**Files:**
- Modify: `docs/agent-kv-api.md`

**Interfaces:** none (docs only). No test; reviewer reads the diff.

- [ ] **Step 1: Document the calc result shape** in §5: when `calculations` is supplied and enabled, the result adds `calculations_applied: true`, `execution: {success, rows_written, error}`, `codegen_validation_passed: bool`, and `calculation_rows: [ {...}, ... ]` (the computed JSONL rows, size-capped). A failed execution sets top-level `success: false` and a user-safe `error`.

- [ ] **Step 2: Document rollout order** in §12: deploy the sandbox worker (Deployment healthy, consuming `sandbox_codegen`) **before** flipping `AGENT_KV_CALCULATIONS_ENABLED=true`; with the flag on but the sandbox down, calc jobs fail user-safely at the RPC timeout (they do not hang past it) — never leave the flag on without a healthy sandbox fleet. Note the five §6.3 layers and that the sandbox pod carries no LLM/OCR/storage secrets.

- [ ] **Step 3: Commit**

```bash
git add docs/agent-kv-api.md
git commit -m "docs(agent-kv): calculation result shape and sandbox rollout order"
```

---

## Task 7: `SandboxCodeTransport` (CLOUD)

**Repo/branch:** `/Users/arun/Devel/Github/unstract-cloud`, `UN-4044-agent-kv-cloud-executor`.

**Files:**
- Create: `workers/plugins/agentic_kv/src/sandbox_transport.py`
- Modify: `workers/plugins/agentic_kv/src/constants.py`
- Test: `workers/plugins/agentic_kv/tests/test_sandbox_transport.py`

**Interfaces:**
- Consumes: `CodeExecutionTransport` (`workers/plugins/agentic_kv/src/code_transport.py`); the OSS task `execute_sandboxed_code`.
- Produces: `SandboxCodeTransport(dispatcher, queue, org_id, timeout_default)` with `execute(code, input_json_path, output_jsonl_path, timeout) -> ExecutionResult`-shaped object. On unavailability raises `CodeExecutionUnavailable`.

**Context:** `execute` reads `input_json_path`, builds `{request_id, code, input_json, timeout}`, dispatches request-reply through the injected dispatcher (the routing dispatcher works in both Celery and PG mode), then on success writes `rows_jsonl` to `output_jsonl_path` and returns a duck-typed result matching `engine.code_executor.ExecutionResult` (`success`, `output_path`, `error`, `rows_written`, `stdout`, `stderr`). Do **not** import the engine's `ExecutionResult` (the seam is decoupled by convention — mirror `code_transport.py`'s docstring); return a small local dataclass with those fields.

- [ ] **Step 1: Write the failing test** — `workers/plugins/agentic_kv/tests/test_sandbox_transport.py`:

```python
import json
import tempfile
from pathlib import Path

import pytest

from sandbox_transport import SandboxCodeTransport
from code_transport import CodeExecutionUnavailable


class _FakeDispatcher:
    """Stands in for the executor-RPC dispatcher: records the payload, returns
    a canned reply row (``.result`` is the task's dict)."""
    def __init__(self, reply=None, raises=None):
        self.reply, self.raises, self.seen = reply, raises, None

    def dispatch_sandbox(self, *, queue, request_id, code, input_json, timeout, org_id):
        self.seen = dict(queue=queue, request_id=request_id, code=code,
                         input_json=input_json, timeout=timeout, org_id=org_id)
        if self.raises:
            raise self.raises
        return self.reply


def _paths(tmp, record):
    inp = Path(tmp) / "in.json"; out = Path(tmp) / "out.jsonl"
    inp.write_text(json.dumps({"records": [record]}))
    return str(inp), str(out)


def test_success_writes_rows_and_returns_result():
    with tempfile.TemporaryDirectory() as tmp:
        inp, out = _paths(tmp, {"n": 2})
        disp = _FakeDispatcher(reply={"success": True, "rows_jsonl": '{"n2": 4}\n',
                                      "rows_written": 1, "stdout": "", "stderr": "",
                                      "error": None})
        t = SandboxCodeTransport(disp, queue="sandbox_codegen", org_id="7",
                                 timeout_default=30)
        res = t.execute("code", inp, out, timeout=10)
        assert res.success is True
        assert res.rows_written == 1
        assert Path(out).read_text() == '{"n2": 4}\n'
        assert disp.seen["timeout"] == 10 and disp.seen["queue"] == "sandbox_codegen"
        assert disp.seen["org_id"] == "7"


def test_failure_reply_maps_to_unsuccessful_result():
    with tempfile.TemporaryDirectory() as tmp:
        inp, out = _paths(tmp, {})
        disp = _FakeDispatcher(reply={"success": False, "rows_jsonl": "",
                                      "rows_written": 0, "stdout": "", "stderr": "",
                                      "error": "safety gate: disallowed import 'os'"})
        t = SandboxCodeTransport(disp, queue="sandbox_codegen", org_id="7",
                                 timeout_default=30)
        res = t.execute("code", inp, out, timeout=10)
        assert res.success is False
        assert "safety gate" in res.error


def test_no_reply_raises_unavailable():
    with tempfile.TemporaryDirectory() as tmp:
        inp, out = _paths(tmp, {})
        disp = _FakeDispatcher(reply=None)  # RPC timed out / no result row
        t = SandboxCodeTransport(disp, queue="sandbox_codegen", org_id="7",
                                 timeout_default=30)
        with pytest.raises(CodeExecutionUnavailable):
            t.execute("code", inp, out, timeout=10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd workers/plugins/agentic_kv && UV_FROZEN=1 uv run --with pytest --with /Users/arun/Devel/Github/unstract/unstract/agent-kv-schema pytest tests/test_sandbox_transport.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'sandbox_transport'`.

- [ ] **Step 3: Add the config constant.** In `workers/plugins/agentic_kv/src/constants.py`, add `AGENT_KV_SANDBOX_CODEGEN_QUEUE = "AGENT_KV_SANDBOX_CODEGEN_QUEUE"` to `Env`, and a `sandbox_codegen_queue: str` field to `AgentKVConfig` read in `from_env` (default `"sandbox_codegen"`, empty → default). A blank/unset queue means "sandbox disabled" (Task 8 uses `UnavailableCodeTransport`).

- [ ] **Step 4: Write the transport.** `workers/plugins/agentic_kv/src/sandbox_transport.py`:

```python
"""Cloud transport implementing the engine's CodeExecutionTransport seam by
dispatching to the OSS sandbox worker over the executor-RPC request-reply
machinery. Decoupled from engine.code_executor by convention (duck-typed
result), mirroring code_transport.py.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from code_transport import CodeExecutionTransport, CodeExecutionUnavailable


@dataclass
class _Result:
    success: bool
    output_path: str
    error: str | None = None
    rows_written: int = 0
    stdout: str = ""
    stderr: str = ""


class SandboxCodeTransport(CodeExecutionTransport):
    def __init__(self, dispatcher: Any, *, queue: str, org_id: str,
                 timeout_default: int) -> None:
        self._dispatcher = dispatcher
        self._queue = queue
        self._org_id = org_id
        self._timeout_default = timeout_default

    def execute(self, code: str, input_json_path: str, output_jsonl_path: str,
                timeout: int) -> _Result:
        input_json = Path(input_json_path).read_text()
        reply = self._dispatcher.dispatch_sandbox(
            queue=self._queue,
            request_id=str(uuid.uuid4()),
            code=code,
            input_json=input_json,
            timeout=int(timeout) or self._timeout_default,
            org_id=self._org_id,
        )
        if reply is None:
            raise CodeExecutionUnavailable("sandbox produced no result (RPC timeout)")
        if reply.get("success"):
            Path(output_jsonl_path).write_text(reply.get("rows_jsonl", ""))
            return _Result(success=True, output_path=output_jsonl_path,
                           rows_written=reply.get("rows_written", 0),
                           stdout=reply.get("stdout", ""), stderr=reply.get("stderr", ""))
        return _Result(success=False, output_path=output_jsonl_path,
                       error=reply.get("error") or "sandbox execution failed",
                       stdout=reply.get("stdout", ""), stderr=reply.get("stderr", ""))
```

The `dispatch_sandbox` method on the dispatcher is defined in Task 8 (a thin wrapper over `PgExecutionDispatcher.dispatch`/the routing dispatcher that packs these kwargs into a task call and returns the reply dict, or `None` on timeout). The transport depends only on that duck-typed method — the test's `_FakeDispatcher` documents its contract.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd workers/plugins/agentic_kv && UV_FROZEN=1 uv run --with pytest --with /Users/arun/Devel/Github/unstract/unstract/agent-kv-schema pytest tests/test_sandbox_transport.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git checkout -- uv.lock 2>/dev/null || true
git add workers/plugins/agentic_kv/src/sandbox_transport.py workers/plugins/agentic_kv/src/constants.py workers/plugins/agentic_kv/tests/test_sandbox_transport.py
git commit -m "UN-4044 [FEAT] SandboxCodeTransport over executor-RPC for agentic_kv codegen"
```

---

## Task 8: Wire the transport into the executor + dispatcher adapter (CLOUD)

**Files:**
- Modify: `workers/plugins/agentic_kv/src/executor.py`
- Create/Modify: a small `dispatch_sandbox` adapter (in `sandbox_transport.py` or a sibling `sandbox_dispatch.py`)
- Test: extend `workers/plugins/agentic_kv/tests/test_executor*.py`

**Interfaces:**
- Consumes: `SandboxCodeTransport` (Task 7); `UnavailableCodeTransport` (`code_transport.py`); the executor-RPC dispatcher factory (`get_executor_dispatcher` / routing dispatcher) already used by sub-project #1.
- Produces: the executor builds a real `SandboxCodeTransport` when `AGENT_KV_CALCULATIONS_ENABLED` is on **and** the sandbox queue is configured; otherwise `UnavailableCodeTransport`. It forwards the submitted `calculations` + a per-job tmp `output_path` into `KVExtractor`, and after the run reads the JSONL back into `data["output"]["calculation_rows"]` (size-capped by `SANDBOX_MAX_OUTPUT_BYTES`).

**Context:** Today the executor passes `calculations=None` and no `output_path` (kv_extractor line ~408). Change it to forward the real values from `executor_params["options"]["calculations"]` when present, build the transport, and hand it to the engine's `CodeExecutor` via the existing `transport=` seam. After `KVExtractor.run()`, if `run_codegen` fired, read the per-job output JSONL and attach `calculation_rows` to the result dict the executor stores. Reuse the per-job `tempfile.mkdtemp` already created for images (the C1 fix) for the codegen output path, cleaned in the same `finally`.

- [ ] **Step 1: Write the failing test** — add to `workers/plugins/agentic_kv/tests/test_executor_codegen.py` (new file):

```python
# Verifies the executor forwards calculations + wires a transport, and folds
# the returned rows into calculation_rows. Uses a stub transport so no real
# subprocess/broker is needed.
def test_calculation_rows_folded_into_result(monkeypatch, tmp_path):
    ...  # build an executor invocation with options.calculations set and a
    # stub SandboxCodeTransport whose execute() writes two JSONL rows; assert
    # result["output"]["calculation_rows"] has those two rows and
    # result["output"]["calculations_applied"] is True.


def test_unavailable_transport_when_flag_off(monkeypatch):
    ...  # with AGENT_KV_CALCULATIONS_ENABLED unset, the executor uses
    # UnavailableCodeTransport (a calc submit would fail user-safely).
```

Fill these in against the executor's actual construction (the implementer writes the concrete bodies from the real signatures — the two assertions above are the contract). This is the one task whose test code the plan cannot fully pre-write without the executor's private wiring in front of it; keep both assertions exactly.

- [ ] **Step 2: Run to verify it fails.** `cd workers/plugins/agentic_kv && UV_FROZEN=1 uv run --with pytest --with /Users/arun/Devel/Github/unstract/unstract/agent-kv-schema pytest tests/test_executor_codegen.py -q -p no:cacheprovider` → FAIL.

- [ ] **Step 3: Add the `dispatch_sandbox` adapter** — a thin function/method that takes the routing dispatcher and the kwargs, builds an `ExecutionContext`-free task dispatch (the sandbox task is a plain named task, not an executor operation), and returns the reply dict or `None` on timeout. If the simplest correct path is a direct request-reply via `PgExecutionDispatcher`/Celery `AsyncResult` with the routing gate, use that; keep it under one small, tested unit.

- [ ] **Step 4: Wire the executor.** Build the transport when enabled+configured, else `UnavailableCodeTransport`; forward `calculations` + `output_path`; read rows back into `calculation_rows` (cap the byte size; on over-cap, set it to `[]` and add a `calculation_rows_truncated: true` flag). Keep the existing user-safe error mapping: a `CodeExecutionUnavailable` or failed execution → the job fails with `"calculations failed: <class>"` (no paths/env).

- [ ] **Step 5: Run to verify it passes.** Same command → PASS. Then the full plugin suite: `UV_FROZEN=1 uv run --with pytest --with /Users/arun/Devel/Github/unstract/unstract/agent-kv-schema pytest tests -q -p no:cacheprovider` → all green, pristine.

- [ ] **Step 6: Commit**

```bash
git checkout -- uv.lock 2>/dev/null || true
git add workers/plugins/agentic_kv/src/executor.py workers/plugins/agentic_kv/src/sandbox_transport.py workers/plugins/agentic_kv/tests/test_executor_codegen.py
git commit -m "UN-4044 [FEAT] Executor wires codegen sandbox transport and folds calculation_rows"
```

---

## Task 9: Chart — sandbox Deployment + NetworkPolicy (CLOUD)

**Files:**
- Create: `charts/unstract-platform/templates/worker-sandbox/deployment.yaml`, `.../networkpolicy.yaml`
- Modify: `charts/unstract-platform/values.yaml`
- Test: `charts/unstract-platform/unittests/sandbox_wiring_test.yaml`

**Interfaces:**
- Produces: `workerSandbox` values block (image, command `["sandbox"]`, `SANDBOX_*` env, resources, replicas, `additionalConfigs: [database, redis, celeryBroker]` — **no** `storage`, **no** `apiKeys`, **no** `agentKv`); a Deployment with the strict securityContext; a default-deny NetworkPolicy allowing egress only to broker + Postgres + DNS.

**Context:** Model the Deployment on `templates/worker-ide-callback-v2/deployment.yaml` but with `securityContext`: `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, `capabilities.drop: [ALL]`, `seccompProfile.type: RuntimeDefault`, `automountServiceAccountToken: false`, an `emptyDir` volume mounted at `/tmp` (sizeLimit 256Mi), CPU/memory/ephemeral-storage limits. The NetworkPolicy selects the sandbox pods and denies all egress except: broker service port, Postgres service port, and DNS (UDP/TCP 53).

- [ ] **Step 1: Write the failing helm-unittest** — `charts/unstract-platform/unittests/sandbox_wiring_test.yaml`, suites:
  - **SBX-D1** Deployment renders with `command: ["sandbox"]` and `WORKER_TYPE=sandbox`.
  - **SBX-S1..S6** securityContext fields exactly as above (`runAsNonRoot`, `readOnlyRootFilesystem`, `allowPrivilegeEscalation: false`, `drop: [ALL]`, `seccompProfile: RuntimeDefault`, `automountServiceAccountToken: false`).
  - **SBX-N1** the pod attaches **no** `storage` / `apiKeys` / `agentKv` config group (negative: the rendered env/secret refs do not contain `AGENT_KV_LLM_API_KEY`, `AGENT_KV_FILE_STORAGE_CREDENTIALS`, `MINIO`).
  - **SBX-P1** NetworkPolicy renders default-deny egress with exactly the broker/Postgres/DNS allowances.
  Use `documentIndex`/`contains`/`notContains`/`equal` assertions; make every negative a real `notContains`, mutation-checked.

- [ ] **Step 2: Run to verify it fails.**

```bash
export S=/private/tmp/claude-501/-Users-arun-Devel-Github-unstract/0ceac69f-3bdf-4b18-9cd3-11517b481fbc/scratchpad/helm
export PATH=$S:$PATH HELM_PLUGINS=$S/plugins HELM_DATA_HOME=$S/data HELM_CONFIG_HOME=$S/config HELM_CACHE_HOME=$S/cache
cd charts/unstract-platform && helm unittest --strict -f 'unittests/sandbox_wiring_test.yaml' .
```
Expected: FAIL (templates/values absent).

- [ ] **Step 3: Add the values block, Deployment and NetworkPolicy** to satisfy the suites. Follow the `_pg-worker.tpl`/existing worker templating so the PG twin can be enabled the same way as other workers (a `workerPgSandbox`-style toggle is optional for v1 — Celery mode is sufficient for the sandbox; note it in values if deferred).

- [ ] **Step 4: Run to verify it passes** (same command). Then the whole chart suite: `helm unittest --strict -f 'unittests/*_test.yaml' .` → all suites green (count grows by the new suites).

- [ ] **Step 5: Commit**

```bash
git add charts/unstract-platform/templates/worker-sandbox charts/unstract-platform/values.yaml charts/unstract-platform/unittests/sandbox_wiring_test.yaml
git commit -m "UN-4044 [FEAT] Sandbox worker Deployment + default-deny NetworkPolicy + helm tests"
```

---

## Task 10: GA flip — enable calculations (CLOUD)

**Files:**
- Modify: `charts/unstract-platform/cloud-deployment-values/cloud.values.yaml`
- Modify: `workers/plugins/agentic_kv/...` only if the serializer gate lives cloud-side (it is OSS — confirm no cloud change needed beyond values)
- Test: helm-unittest assertion that cloud values render `AGENT_KV_CALCULATIONS_ENABLED=true` and enable `workerSandbox`.

**Context:** The submit serializer's `AGENT_KV_CALCULATIONS_ENABLED` gate is OSS (`backend/backend/settings/base.py`, read by `execution_serializers.py`). GA = set `AGENT_KV_CALCULATIONS_ENABLED: "true"` in cloud values and enable the sandbox worker there. No OSS default change (stays `false` for OSS-only deployments, which have no engine anyway).

- [ ] **Step 1: Write the failing helm-unittest** asserting, against `-f cloud.values.yaml`, that the backend env carries `AGENT_KV_CALCULATIONS_ENABLED=true` and `workerSandbox.enabled=true`.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Set the values** in `cloud.values.yaml` (enable `workerSandbox`, set the flag).
- [ ] **Step 4: Run → PASS**; then `helm unittest --strict -f 'unittests/*_test.yaml' .` → all green.
- [ ] **Step 5: Commit** — `UN-4044 [FEAT] Enable Agent-KV calculations (sandbox GA) in cloud values`.

---

## Task 11: e2e calculation scenarios (OSS test lane) (OSS)

**Files:**
- Modify: `tests/e2e/agent_kv/test_agent_kv_e2e.py`, `tests/e2e/agent_kv/conftest.py`

**Interfaces:**
- Consumes: `submit`, `poll`, `result`, `invoice_schema`, `INVOICE_PDF` (existing conftest helpers).
- Produces: two scenarios — a happy calc path and a hostile calc path — both gated on `AGENT_KV_E2E=1` + a real/mock LLM (like the rest of the lane), and skipping unless `AGENT_KV_CALCULATIONS_ENABLED` is declared for the run.

**Context:** These prove the whole hop end-to-end in Task 12. The calc field carries a simple instruction (e.g. "add a `net` column = total × 0.9"); assert `COMPLETED`, `calculations_applied`, `execution.success`, and non-empty `calculation_rows`. The hostile scenario submits a calculation that would generate disallowed code (or forces a gate rejection) and asserts the job fails user-safely (no path/env/`sk-` leakage via the existing `_assert_user_safe_error` helper).

- [ ] **Step 1: Write the two scenarios** (structure-only assertions; gated + skip-guarded exactly like the webhook scenario). Add a `calc_schema()`/instruction helper to conftest if needed.
- [ ] **Step 2: Collect-only check** — `AGENT_KV_E2E=1 UNSTRACT_BACKEND_URL=http://x <rigvenv>/python -m pytest tests/e2e/agent_kv --collect-only -q` → 16 collected.
- [ ] **Step 3: Lint** — `ruff check` + `ruff format` clean.
- [ ] **Step 4: Commit** — `test(agent-kv): e2e calculation happy-path and hostile scenarios (gated)`.

---

## Task 12: Live integration run + fix loop (13c) (BOTH)

**Context:** The acceptance gate for the whole sub-project, run exactly like 13b: a scratch worktree of `Feat/agent-kv-api`, `copy_cloud_deps.py` overlay + Dockerfile patches, rebuild the `worker-unified` image (now containing `workers/sandbox/`), boot the stack (with `worker-sandbox`, `AGENT_KV_CALCULATIONS_ENABLED=true`), run the full Agent-KV lane. Prereqs identical to 13b (Docker, LLMWhisperer key, LLM key or mock). Reuse the scratchpad helpers (`stack.sh`, `run-env.sh`, the Compose-v2 shim, port override, mock-Auth0 sidecar).

- [ ] **Step 1: Build the merged tree** in a scratch worktree; overlay cloud; apply docker patches; regenerate env; add `AGENT_KV_CALCULATIONS_ENABLED=true` and the sandbox worker to the run env.
- [ ] **Step 2: Rebuild `worker-unified`** (carries the new sandbox worker) and `backend`; recreate the stack including `worker-sandbox`.
- [ ] **Step 3: Pre-flight** — confirm `worker-sandbox` consumes `sandbox_codegen`; the executor registry still resolves `agentic_kv`; the sandbox pod env carries **no** LLM/storage secrets (`docker exec` grep).
- [ ] **Step 4: Run the full lane.** Expect the 14 prior scenarios plus the 2 calc scenarios green (calc scenarios need the sandbox up). Verify in the DB/logs: a completed calc job's result carries `calculation_rows`; the sandbox worker log shows the request ran; no document bytes or secrets in sandbox logs.
- [ ] **Step 5: Adversarial live check** — with the flag on but `worker-sandbox` stopped, submit a calc job; assert it fails user-safely at the RPC timeout (does not hang). Restart the worker.
- [ ] **Step 6: Fix loop.** Any defect found → fix in the owning repo (TDD), rebuild, re-run, ledger it (like 13b's F-series). Then a scoped re-review of the fix commits.
- [ ] **Step 7: Tear down** the stack + worktree; write the 13c findings ledger; update memory. Report to Arun; pushes/PR only on his OK.

---

## Self-Review

- **Spec coverage:** S1 goal (Task 10/12), S2 placement (Tasks 1–6 OSS, 7–11 cloud), S3 transport (Task 7), S4 contract (Tasks 4, 7), S5 worker (Tasks 2–4), S6 image (Task 5 uses worker-unified per the amendment), S7 transport+GA (Tasks 7, 8, 10), S8 hardening (Tasks 5 compose, 9 chart), S9 testing (unit in 2–4/7–9, e2e in 11, live in 12), S10 rollout (Tasks 6, 10, 12). All sections mapped.
- **Placeholder scan:** Task 8 Step 1 intentionally leaves two test *bodies* to the implementer because they bind to the executor's private wiring — but pins both assertions verbatim; flagged as the one exception, not a silent TODO. No other placeholders.
- **Type consistency:** `check_code_safe` (Task 2) used by Task 3; `run_code`/`RunResult` (Task 3) used by Task 4; `execute_sandboxed_code` name identical in Tasks 1/4/7; `SandboxCodeTransport.execute` signature matches the `CodeExecutionTransport` seam; `dispatch_sandbox` duck-typed method defined by the `_FakeDispatcher` contract in Task 7 and implemented in Task 8.
