# Agent-KV Codegen Sandbox Worker — Design (Sub-project #2)

Date: 2026-09-01. Status: approved design (brainstormed with Arun; approach and all
sections approved in chat). Parent: `2026-08-28-agent-kv-api-design.md` §6.3 (normative
security model, D9) and the cloud executor design (`unstract-cloud`
`docs/superpowers/specs/2026-08-29-agent-kv-cloud-executor-design.md`, seam C-series).

## 1. Goal and scope (S1)

Ship the dedicated hardened sandbox worker that executes engine-generated calculation
code, and take the API's `calculations` field to **GA in one cycle**:
`AGENT_KV_CALCULATIONS_ENABLED=true` at the end, proven by live e2e. Explicitly out of
scope (follow-ups): migrating `agentic_table` onto this sandbox (verified 2026-09-01:
it currently executes generated code **in-process via subprocess** in the worker pod —
the latent finding §6.3 anticipated; the interface here is built to serve it), the
Prompt Studio enforce_type, gVisor/`runtimeClass`, per-job K8s Jobs.

## 2. Placement (S2)

The sandbox worker is **OSS** (`Zipstack/unstract`, branch `Feat/agent-kv-api`):
generic infrastructure — a hardened queue consumer that runs stdlib-only Python against
JSON — usable by OSS deployments and tested by the OSS rig. The cloud half shrinks to
the `SandboxCodeTransport` in the `agentic_kv` plugin + chart wiring + the flag flip
(new Jira ticket, to be assigned).

## 3. Transport mechanism (S3)

Request-reply over the **existing executor-RPC machinery**
(`unstract.workflow_execution.executor_rpc`: `PgExecutionDispatcher` — unique
`reply_key`, poll `pg_task_result`, timeout, at-least-once + caller-timeout — with
`RoutingExecutionDispatcher` falling back to Celery), on a dedicated queue. Rejected:
Celery-only `AsyncResult.get()` (breaks in PG-queue mode — the mode cloud runs; known
deadlock foot-gun) and an HTTP microservice (violates §6.3's broker-only egress;
new in-cluster auth surface).

## 4. Task contract (S4)

One task, `execute_sandboxed_code`, queue `sandbox_codegen` (+ PG twin per the
`workerPg*` conventions). Request — every cap re-enforced server-side regardless of
what the caller sent:

```json
{
  "request_id": "<uuid — opaque correlation only; no org/tenant identifiers (§6.3)>",
  "code": "<generated Python, cap SANDBOX_MAX_CODE_BYTES (64 KiB default)>",
  "input_json": "<record JSON, inline, cap SANDBOX_MAX_INPUT_BYTES (1 MiB default)>",
  "timeout": 30
}
```

Reply: `{"success": bool, "rows_jsonl": "<inline, cap SANDBOX_MAX_OUTPUT_BYTES (1 MiB
default)>", "rows_written": int, "stdout": "<4 KiB trunc>", "stderr": "<4 KiB trunc>",
"error": "<user-safe>"}`.

Inline payloads keep object storage entirely out of the sandbox's reach: it sees only
record + code — never the document, the schema, or tenant identity. At-least-once
redelivery is safe: the code is a pure transform (no side effects to duplicate).

## 5. The worker (S5) — `workers/sandbox/`

`WorkerType.SANDBOX`, built like `ide_callback` (`worker.py` via `WorkerBuilder`,
`tasks.py` with the single task), plus `runner.py`, the hardened harness enforcing
§6.3's layers **server-side**:

1. **AST gate** — the **normative copy lives in the worker**; the engine's
   `_check_code_safe` stays as client-side pre-flight, with cross-reference comments
   both ways (S6: deliberate duplication of a small security control; the sandbox
   never trusts the client's check).
2. **Scrubbed subprocess** — per-request tempdir; `sys.executable -I -S -E` with an
   **empty environment** (minimal PATH), cwd = tempdir, `start_new_session`;
   `preexec_fn` sets rlimits: CPU (= timeout), address space
   (`SANDBOX_MEMORY_MB`, 512 default), NPROC (small), NOFILE, FSIZE (= output cap).
   Process group killed at wall-clock `timeout + grace`. The runner stub is **the same
   stub contract the engine's `CodeExecutor` uses today** — codegen prompts do not
   change.
3. **Output discipline** — JSONL validated line-by-line (`json.loads` each line),
   row- and byte-capped, returned inline. Errors are mapped to user-safe strings
   (class + stage; no paths, no env, no raw stderr beyond the truncated field).

Config env (all `SANDBOX_*`): `MAX_CODE_BYTES`, `MAX_INPUT_BYTES`,
`MAX_OUTPUT_BYTES`, `MAX_ROWS`, `TIMEOUT_MAX` (server clamp), `MEMORY_MB`,
concurrency. Registered in `worker_enums_base` / `registry.py` (queue + task route),
`workers/sample.env`, dev compose, and the rig.

## 6. Image (S7 — amended 2026-09-01, approved by Arun)

v1 runs the sandbox worker from the **existing `worker-unified` image** (command
`sandbox`), like every other worker: the `workers` package (queue consumers,
`WorkerBuilder`) depends on SDK1/connectors/core, so a truly minimal image requires a
disentangled standalone mini-worker — deferred. The guarantees that matter do not
depend on image contents: the generated-code subprocess runs with a scrubbed empty
env; the pod mounts **no secrets beyond the broker/DB credential** (no `agentKv`, no
`storage` groups); egress is default-denied. A dedicated python-slim image (no SDK1,
no LLM libraries, no platform clients) moves to the **upgrade path** alongside
gVisor/`runtimeClass` and per-job K8s Jobs.

## 7. Cloud transport + result surfacing + GA (S8, S9)

`SandboxCodeTransport(CodeExecutionTransport)` in `workers/plugins/agentic_kv/`
(cloud): builds the payload, dispatches request-reply via the routing dispatcher,
writes returned rows to the local `output_jsonl_path`, maps failure to the
`ExecutionResult`-shaped duck object. Timeout / queue unconfigured →
`CodeExecutionUnavailable` → the existing user-safe stage-error path.
`UnavailableCodeTransport` remains the fail-closed default whenever
`SANDBOX_CODEGEN_QUEUE` (default `sandbox_codegen`) is unset/disabled.

The executor stops passing `calculations=None`: it forwards the submitted
`calculations` and a per-job tmp `output_path` into `KVExtractor` (`run_codegen`
activates), and after the run reads the JSONL back and embeds it in the stored result
as `calculation_rows` (size-capped), alongside the engine's existing
`calculations_applied` / `execution{success, rows_written, error}` /
`codegen_validation_passed` fields (kv_extractor result contract, verified). A failed
execution already fails the job user-safely (`out["success"]=False`).

GA flip (S9): backend `AGENT_KV_CALCULATIONS_ENABLED=true` in cloud values + test
compose; the serializer un-gates the field; docs §3/§5/§12 updated. The frozen
OSS↔cloud `executor_params` contract already carries `options.calculations` — no
contract change.

## 8. Hardening (chart) (S10)

New `sandbox` Deployment: `runAsNonRoot`, `readOnlyRootFilesystem` + sized `emptyDir`
at `/tmp` (256 Mi default), all capabilities dropped, `seccompProfile:
RuntimeDefault`, `automountServiceAccountToken: false`, CPU/memory/ephemeral-storage
limits, replicas/HPA values. Dedicated **NetworkPolicy**: default-deny ingress+egress;
egress only to broker (RabbitMQ), Postgres (PG twin + result rows), DNS. No MinIO/GCS,
no platform-service, no backend, no internet. Secrets: only the broker/DB credential
(own Secret) — none of the `agentKv` or `storage` groups (negative helm-unittest
assertions, mutation-checked). Compose/dev mirrors what it can (`read_only`,
`cap_drop: ALL`, `no-new-privileges`, tmpfs `/tmp`, internal network only).

### 8a. Accepted v1 residual — arbitrary in-pod file reads (R12)

Generated calculation code legitimately needs `open()` (it reads its input JSON and
writes its output JSONL), and the AST gate's import allowlist includes `pathlib` — so
untrusted code **can read any world-readable file in its own pod** and emit the
contents as a calculation row. This is **not robustly closable at the AST layer**
(`open`, `pathlib`, `io`, `json.load(open(...))` are all needed or reachable), so v1
**accepts it** as a bounded residual, contained by layers 2–5 rather than layer 1:

- the pod carries **no secrets** (§8 / R11 — no LLM/OCR/storage creds, and critically
  not the platform master `ENCRYPTION_KEY`; only its own broker/result-backend DB
  credential),
- it runs **non-root** on a **read-only rootfs** (cannot read `/etc/shadow`, cannot
  write outside the `/tmp` emptyDir),
- **default-deny egress** (no network path to exfiltrate what it reads),
- **per-job tempdir** isolation (no cross-tenant file access), and
- results return **only to the submitting customer's own API key**.

So the worst case is disclosure of a **non-sensitive container file** (e.g. a stock
`/etc/passwd`) back to the customer who submitted the job — no secret, no cross-tenant
read, no exfiltration. The **deferred mitigation is `runtimeClass: gvisor`** (a
filesystem/syscall sandbox), already listed as a v1-out-of-scope upgrade in §1 and the
parent design §6.3. This residual is the reason the NetworkPolicy's default-deny egress
and the no-secrets invariant are load-bearing and must not be relaxed.

## 9. Testing (S11)

- Worker unit: AST-gate adversarial corpus (`os`/`subprocess`/`socket`/`ctypes`
  imports, `eval`/`exec`/`__import__`, encoded payloads); harness hostile-behavior
  suite — infinite loop (wall-clock kill), memory balloon (rlimit), fork attempt
  (NPROC), oversized output (FSIZE + truncation), stdout flooding, non-JSON output;
  happy transform; empty-subprocess-env assertion.
- Cloud transport unit: payload/caps, timeout → `CodeExecutionUnavailable`,
  rows written back, error mapping.
- Integration: rig group running the real harness (real subprocesses; no broker).
- e2e (Agent-KV lane): a gated `calculations` happy-path scenario (simple arithmetic
  over the invoice; asserts `COMPLETED`, `calculations_applied`, `execution.success`,
  computed `calculation_rows`) and a hostile-calculation scenario (job fails
  user-safely; no path/env leakage). Both proven in a live "13c" run at the end,
  13b-style.

## 10. Rollout (S12)

OSS first (worker + image + compose + rig + docs, on `Feat/agent-kv-api`), then cloud
(transport, chart, flag) under the new ticket. Deploy order in docs §12: sandbox
Deployment healthy → flag on. Flag off degrades cleanly (submit rejects
`calculations`; nothing dispatches mid-pipeline). Prove in the live run that a stack
with the flag on but the sandbox down fails the calc stage user-safely rather than
hanging past the RPC timeout.

## 11. Open items

- ~~Jira ticket for the cloud half~~ — resolved 2026-09-01: **UN-4044** (same ticket as
  sub-project #1), cloud work continues on `UN-4044-agent-kv-cloud-executor`; OSS work
  continues on `Feat/agent-kv-api`.
- Exact resource defaults (CPU/memory/replicas) — set at implementation, revisited
  after the live run's measurements.
- `agentic_table` migration onto this sandbox — follow-up sub-project.
