# Agent-KV: Agentic Key-Value Extraction API — Design

- **Date:** 2026-08-28 (rev. b — amended after adversarial feasibility review against the codebase)
- **Status:** Draft for review
- **Owner:** Arun Venkataswamy
- **Scope of this document:** the whole feature (OSS + cloud halves). The implementation
  plan derived from it covers the OSS half (this repo); the cloud-plugin half is planned
  separately in the cloud repo.

## 1. What and why

Expose the agentic KV extraction system built in `unstract-agentic-table` (`src/kv`) as a
metered, API-first product on the Unstract platform: upload a document plus a `keys.json`
schema, get a job id, poll a verbose agent-centric status, fetch a rich result (record +
per-field QA/challenger audit trail). Billed per page plus LLM cost via the existing
billing pipeline, with a new Stripe product on the cloud side.

The engine is proven (QA pass, adversarial challenger, constraint checking, normalizers,
opt-in codegen post-processing). This design is about *hosting* it safely and metering it
— not about changing how it extracts.

## 2. Locked decisions

These were settled in the brainstorming discussion and are not open for re-litigation in
the implementation plan:

| # | Decision |
|---|---|
| D1 | v1 is **KV only**. Table extraction may later ride the same substrate; not now. |
| D2 | The **calculations/codegen path is in scope** for v1 (opt-in per request). |
| D3 | The extraction engine ships as a **cloud executor plugin** (like `agentic_table`), discovered via entry points, invoked through the executor dispatcher. This repo carries the API scaffold, which **fails closed** with a clear error when the plugin is absent. |
| D4 | Public surface is **`POST /agent-kv/`** with `Bearer` key auth, same DX family as existing APIs. |
| D5 | A dedicated **`AgentKVKey`** model; keys are managed in the same area as Platform API key management. Org-scoped, rotatable. |
| D6 | LLM selection is **system-level, env-configured only** (`AGENT_KV_LITE_MODEL`, `AGENT_KV_ADVANCED_MODEL` + provider keys in worker env). No end-user model control. The engine keeps its LiteLLM client. |
| D7 | All engine **caching is account-level** (org-scoped cache keys). |
| D8 | **MCP is parked** for v1. The serializer+helper structure keeps it a cheap bolt-on later. |
| D9 | Codegen executes only in the **dedicated sandbox worker** (§6.3). No in-process execution, no Docker-daemon dependency, anywhere. |
| D10 | Compliance/retention tuning is deferred; **engineering defaults** (config-overridable): uploaded document deleted on job completion; results retained 7 days. |
| D11 | Results are **re-readable until TTL** (deliberate divergence from the one-shot 406 pattern of workflow API deployments), plus explicit `DELETE`. |
| D12 | One document per job in v1. Batch = N calls. |
| D13 | Billing: the platform only **meters** (PageUsage + per-agent Usage rows tagged `product=agent_kv`). Price construction, cache-hit discounts, and failed-job policy are cloud-side policy over meter rows. |

## 3. Non-goals (v1)

- Table extraction API (D1). No `json_structure`/table mapping codegen — the KV record
  mirrors `keys.json` by construction, so codegen exists only for `calculations`.
- MCP tools (D8), frontend UI, HITL review queue integration, batch endpoints,
  per-field live streaming of status, retrieval/RAG, user model selection.
- Compliance-driven retention/residency work (D10).
- Reconciling with the future `agent_kv` Prompt Studio enforce_type — designed *for*
  (shared executor, §5.2) but not implemented now.

## 4. Background: the engine being productized

`unstract-agentic-table/src/kv` pipeline (stage-sequential):

```
document_processor → key_extractor (+ array_extractor) → [kv_qa] → [kv_challenger]
    → normalizers → constraints → [code_generator → code_executor]   (bracketed = optional)
```

- OCR: LLMWhisperer V2 (`mode=form`, layout-preserving, hex line numbers — grounding/QA
  depend on them) + pypdfium2 page images (DPI 150). Excel OCR'd text-only.
- LLM: LiteLLM, two tiers (`lite_model`/`advanced_model`), streaming, retry/backoff,
  truncation fail-loud, optional forced tool-use.
- Result object: `record`, `normalized_record`, per-field `keys[]` audit trail
  (qa_status/attempts, challenge_status/attempts/reason, provenance), `qa_passed`,
  `challenge_passed`, `consistency_violations`, `cost_summary` (per-agent tokens+USD),
  `timing` (per stage).
- Codegen is gated: `run_codegen = (calculations is not None) and (output_path is not None)`
  (`kv_extractor.py:64`). No calculations ⇒ no code is ever generated or executed.
- Cache tiers: documents / extraction / codegen-prompt / codegen.

## 5. Architecture

### 5.1 Component map

```
                    ┌────────────── this repo (OSS) ──────────────┐
  client ──POST──▶  agent_kv Django app                           │
                    │  • public execution urls (new prefix)       │
                    │  • AgentKVKey model + management urls       │
                    │  • AgentKVJob model (status, stages, meta)  │
                    │  • serializers (validate, compile keys.json)│
                    │  • dispatch via resolve_transport           │
                    │  • results persistence + TTL, usage emission│
                    └───────────────┬─────────────────────────────┘
                                    │ ExecutionContext(executor_name="agentic_kv")
                                    ▼
                    ┌───────────── cloud repo (plugin) ───────────┐
                    │ agentic_kv executor (entry-point plugin)    │
                    │  • ported src/kv engine                     │
                    │  • env-LiteLLM client (D6)                  │
                    │  • org-scoped cache backend (D7)            │
                    │  • CodeExecutionTransport ──▶ sandbox queue │
                    ├─────────────────────────────────────────────┤
                    │ agent-kv sandbox worker (own Deployment)    │
                    │  • AST gate + scrubbed-env subprocess       │
                    │  • hardened pod, deny-all egress (§6.3)     │
                    └─────────────────────────────────────────────┘
```

The OSS app is fully functional scaffolding: it validates, creates jobs, dispatches, and
serves status/results.

**Schema compiler lives in OSS — single source of truth.** The `keys.json` schema
compiler (pure stdlib, ~150 lines: `kv_schema` + `validators` from the source project) is
ported into the OSS `agent_kv` app. It is the one engine component in this repo: submit-time
compilation, the `/validate` endpoint, and the §6.1 structural caps all need it. The cloud
engine **imports** this OSS compiler instead of keeping its fork (cloud plugins already
depend on OSS packages — this is the normal dependency direction), so the schema language
cannot drift between the API's validation and the engine's execution.

**Fail-closed gating.** The Django backend cannot see the executor plugin registry — that
lives in the workers process (entry-point discovery in `workers/executor/executors/`), and
dispatching `executor_name="agentic_kv"` with no plugin deployed would enqueue to a queue
no worker consumes and hang, not error. Gating therefore happens **before enqueue, in the
backend**, via a backend-visible capability marker: the cloud deliverable includes a small
backend plugin package probed with the existing `plugins.get_plugin(...)`/try-import
pattern (as `subscription_usage` and `pluggable_apps.agentic_studio_registry` do). The
submit view returns HTTP 501 "agent-kv engine not available on this deployment" when the
probe fails.

### 5.2 Why an executor, and the shared-codebase story

`agentic_table` set the precedent: a cloud executor plugin registered via entry points
(`workers/executor/executors/__init__.py`), dispatched with
`ExecutionContext(executor_name=..., operation=..., executor_params=...)` through
`get_executor_dispatcher` — the same seam Prompt Studio and the structure tool already
use, with PG-queue/Celery routing, fairness headers, and usage recording included.

Agent-KV registers `executor_name="agentic_kv"`, `operation="kv_extract"`. When the
Prompt Studio `agent_kv` enforce_type is built (by another engineer, near-term), it
dispatches to the **same executor** with a second entry operation. To make that work
without speculative code, the engine takes its LLM configuration via a small injected
config object: env-LiteLLM for this API (D6), adapter-resolved for the enforce_type later
(the pattern `agentic_table` already proved with its `llm_adapter_instance_id` params).

### 5.3 Async dispatch (corrected to the executor-RPC path, not the workflow path)

The workflow-transport rules from UN-3445 (dual `task_id`/`queue_message_id` columns,
payload-carried transport) belong to `WorkflowExecution` and do **not** apply here. The
executor-RPC path is the right one, and it is simpler:

- **Dispatch:** the submit view uses
  `get_executor_dispatcher().dispatch_with_callback(context, on_success=…, on_error=…)`
  — exactly the Prompt Studio pattern (`prompt_studio_core_v2/views.py:458` ff.).
  PG-vs-Celery routing is internal to the dispatcher (org-bucketed Flipt resolution);
  there is exactly one dispatch per job, so "resolve once" holds by construction.
- **Handle:** both transports return a UUID task id on this path (Celery
  `AsyncResult.id`; PG mints `str(uuid.uuid4())`, `executor_rpc.py:319`). AgentKVJob
  stores a **single `task_id` UUID column**.
- **Callbacks (new OSS glue, named deliverables):** an `agent_kv_callback` success/error
  task pair on a dedicated callback queue, registered in the workers task-route registry
  and consumed by the existing callback-worker deployment (the `ide_callback` pattern,
  `workers/ide_callback/tasks.py`). The callbacks persist the result, finalize status,
  write `usage_summary`, release the concurrency slot (§6.1), and fire the webhook.
- **Enqueue failure = job failure at submit:** on the PG path a failed enqueue means
  `on_error` never fires (`executor_rpc.py` documents this), so the view wraps dispatch
  in try/except and terminalizes the job itself (Prompt Studio's pattern).
- **`timeout` (§7.1) has no wait primitive** under `dispatch_with_callback`: the view
  polls the AgentKVJob row (written by callbacks/stage reports) up to the deadline.
- Stamp `dispatched_at` positively on successful dispatch; a periodic sweep
  terminalizes never-dispatched jobs (the 967-stuck-executions incident from the
  workflow sweep applies to any create-then-dispatch window; scheduling home in §5.4).
- Codegen fan-out (executor → sandbox queue) uses `queue_backend.dispatch` with the
  execution's resolved backend override.
- Logs go through `LogPublisher` (transport-agnostic).
- **Cloud deploy config:** the executor worker fleet's queue env must add the
  `agentic_kv` executor queue (queues are env-set; defaults only include `legacy`).

### 5.4 Job lifecycle and state

`AgentKVJob` (new model, this repo): `id` (UUID4), `organization` FK, `api_key` FK,
`task_id` (single UUID, §5.3), `status` (PENDING → DISPATCHED → RUNNING → COMPLETED |
FAILED | CANCELLED; RUNNING is written by the first executor stage report), `stage`,
`stages` (JSONB: per-stage status/timing/counters, written by the executor via the
internal API), `pages_total`, `input_ref` (object-store path), `result_ref`,
`usage_summary` (denormalized cost/tokens snapshot), `error` (user-safe message),
`dispatched_at`, `created_at`, `completed_at`, `expires_at`, `tags`, `custom_data`,
`webhook_url`. Terminal states are write-guarded: once COMPLETED/FAILED/CANCELLED, no
callback or stage report may overwrite (this is what makes cancel and at-least-once
delivery safe).

Documents stage in prefix- and org-rooted object-store paths
(`{AGENT_KV_STORAGE_DIR_PREFIX}/{org_id}/{job_id}/`, default prefix `unstract/agent_kv`;
the engine's OCR cache shares the root as `{AGENT_KV_STORAGE_DIR_PREFIX}/{org_id}/cache/`)
via a new `FileStorageType.AGENT_KV` in the shared `unstract/filesystem` package with its
own creds env mapping — a small cross-package change; the existing types and path helpers
are workflow-coupled. The prefix is bucket-rooted like
`WORKFLOW_EXECUTION_DIR_PREFIX`/`API_EXECUTION_DIR_PREFIX`: s3fs/gcsfs read the first
segment as the bucket, so a bucket-less root fails every write with `NoSuchBucket`, and
backend and executor must be configured with the same value. Queue payloads carry
references, never bytes. Results persist to the object store with a DB pointer (not
Redis-only), enabling D11 re-reads.

Stage progress: the executor reports stage transitions through the existing internal API
pattern (workers → `/internal/v1/agent-kv/...`, guarded by `InternalAPIAuthMiddleware`),
idempotent upserts (at-least-once delivery; get_or_create precedent in
`file_execution/internal_views.py`).

**Periodic jobs and their scheduling home** (OSS has no generic per-app scheduler; Beat
is being retired): the never-dispatched sweep and the TTL cleanup (expired results +
leftover inputs) are internal endpoints (`/internal/v1/agent-kv/sweep/`,
`/internal/v1/agent-kv/ttl-cleanup/`) driven by the PG-scheduler/reaper periodic-task
mechanism — the same pattern as the workflow undispatched sweep and `dashboard_metrics`.
Handlers are idempotent (at-least-once delivery).

## 6. Security model (approved)

Premise: **the document, `keys.json`, `key_notes`, and `calculations` are all
attacker-controlled**, and they flow into prompts and codegen. Assume a hostile key
holder and a hostile document independently.

### 6.1 API edge

- New top-level public prefix; middleware bypass means **views own auth** — documented,
  with regression tests that every endpoint 401s without a valid key (MCP test pattern).
- `Bearer <AgentKVKey>`: org-scoped, rotatable, managed alongside platform keys (D5).
- IDOR: job ids are UUID4 **and** every lookup filters by the key's org; unknown and
  forbidden both → 404.
- Fail fast before paid work: file-type allowlist (PDF/XLSX/XLS/images), file-size cap,
  **local page count before OCR** vs. page cap — via `pdfplumber`, already available
  through the sdk1 dependency (no new native dep; pypdfium2 is not in any pyproject).
  Page cap applies pre-OCR to PDFs/images; Excel has no page concept pre-OCR — it is
  capped by file size up front and by OCR-reported virtual pages afterwards (job fails
  before any LLM stage if over cap). Plus `keys.json` compile + structural caps (max
  leaves, array columns, nesting depth, regex length) and max `calculations` bytes.
- Per-org concurrent-job limit: the `APIDeploymentRateLimiter` mechanism is generic
  enough to reuse, but agent-kv gets its **own Redis key namespace and its own limit
  source** (not pooled into API-deployment capacity), with the slot released in the
  terminal callback and backstopped by the sweep (the limiter's slots otherwise leak
  for their 6h TTL). Note: that limiter fails open on Redis errors — acceptable for
  concurrency limiting; quota admission stays fail-closed at §6.6. The per-**key**
  request rate limit is **new code** (no such limiter exists today); 429 on both.
- `/validate` is authenticated (valid key required) and rate-limited — free of charge
  is not free of auth; an open compile endpoint would be a probing/DoS surface.

### 6.2 LLM path

Agents have no tools and no agency: LLM output is parsed into the record, never
executed, never used to call platform APIs, never crosses jobs. Injection therefore
corrupts only the attacker's own result — except two escalation channels, each closed:

1. **Injection → codegen** (document shapes the record; record + calculations feed the
   code generator): all generated code goes through §6.3, no trusted-caller bypass.
2. **Injection → audit trail** (challenger/QA reasons quote document text into status
   output): treated as untrusted text wherever rendered.

### 6.3 Codegen sandbox (normative — D9)

Five mandatory layers:

1. Fail-closed AST gate (existing `_check_code_safe`, kept and regression-tested).
2. Subprocess with **scrubbed environment** (empty env, minimal PATH).
3. Hardened pod: `runAsNonRoot`, `readOnlyRootFilesystem` + per-job `emptyDir` tmp, all
   capabilities dropped, `seccompProfile: RuntimeDefault`,
   `automountServiceAccountToken: false`, CPU/memory/PID limits, wall-clock timeout.
4. NetworkPolicy: default-deny egress except the broker.
5. No secrets in the pod beyond a broker credential scoped to the sandbox queues; the
   scrubbed subprocess env hides even that from generated code.

The sandbox receives only the record JSON + generated code (opaque job ref; no document,
no schema, no tenant identifiers). Output is validated as JSONL and size-capped.
Stdlib-only image (`python:slim`-class, nothing installed).

It is a plain Deployment consuming a dedicated queue — **no Docker daemon, no
docker.sock, no DinD, no privileged pods, no per-job container spawning**. Compose/dev
runs the same worker as a service on an isolated internal network. The ported engine
**deletes** `CodeExecutor`'s environment-sniffing transport (docker-run vs direct-exec
fallbacks) and replaces it with a `CodeExecutionTransport` interface whose production
implementation is the sandbox queue dispatch. Upgrade paths (not v1): `runtimeClass:
gvisor`; per-job K8s Jobs.

Open verification (does not block this design): confirm what the production
`agentic_table` executor does with generated table-mapping code today. If it executes
in-process, that is a latent finding there; this sandbox worker is designed to be shared
by both engines and the future enforce_type.

### 6.4 Workers and data

- Executor worker holds the system LLM keys: own Deployment + Secret, not shared with
  backend or sandbox.
- No document bytes through the broker; org-prefixed object-store staging; deletion on
  completion + TTL sweep (D10).
- Log hygiene: no document content or extracted values in logs; debug traces org-scoped,
  object-store-persisted, flag-gated.

### 6.5 Cache isolation (D7)

Cache key = `org_id + sha256(document) + canonical-hash(keys.json) + engine_version +
model_ids + mode_flags (qa, challenge, extraction_mode, structured_output, page range)`.
Org in the key makes cross-tenant reuse structurally impossible; versions/flags in the
key prevent stale-config replay (the FileHistory lesson).

### 6.6 Billing integrity

- Worst-case job spend bounded pre-dispatch (page cap × known pricing); admission gated
  by the cloud subscription plugin — **fail-closed**. Precision from review: the only
  OSS subscription seam today (`utils/subscription_usage_decorator.py`) is fail-*open*
  and keyed on file executions; the fail-closed reserve check for agent-kv is **new**,
  provided by the cloud plugin and invoked by the submit view only when the §5.1
  capability probe succeeds (OSS-only deployments 501 before ever reaching it).
- All cost figures measured server-side; nothing cost-related read from the request.
- Alerts: AST-gate rejection spikes, 401 bursts, repeated max-page submissions.

### 6.7 Webhook egress (SSRF)

`webhook_url` is a server-side request to a user-supplied URL — an SSRF vector without
controls. Mandatory: resolve the host and refuse private/link-local/loopback/metadata
ranges (re-checked at connect time, not just at validation, to block DNS rebinding);
scheme allowlist (https, plus http only for explicitly configured dev environments); no
redirect following; short timeout; bounded retries; the response body is never read
beyond a status code; payload is `{job_id, status}` only (§7.1). Delivered from the
callback worker, which holds no platform secrets beyond its queue credential.

### 6.8 Inherited test patterns

Credential-leak test (seed fake secrets, drive every read path, fail on leak);
unauthenticated-access tests per endpoint; AST-gate escape corpus (regression suite, not
a soundness proof — the sandbox carries the real weight).

## 7. API contract (approved)

### 7.1 Submit — `POST /agent-kv/` (multipart)

| Field | Required | Notes |
|---|---|---|
| `file` | yes | One document per job (D12). |
| `keys` | yes | `keys.json` (file part or inline JSON string). Compiled synchronously; invalid ⇒ 400, nothing billed. |
| `document_class` | no | Free-text hint (as CLI). |
| `key_notes` | no | Free-text notes appended to the prompt (as CLI). |
| `calculations` | no | Post-processing instructions; opt-in codegen (§6.3). |
| `page_start`, `page_end` | no | 1-based inclusive range. |
| `qa` | no | Default **on**. |
| `challenge` | no | Default **on** (~doubles LLM spend; meter records what ran). |
| `extraction_mode` | no | `whole-doc` (default) \| `per-page`. |
| `structured_output` | no | Default off. |
| `timeout` | no | Omitted or `0` = pure async (immediate 202). `1–300`: the view polls the job row up to the deadline (§5.3) and returns the result inline if the job completes, else 202 with the job id. |
| `tags`, `custom_data` | no | Echoed through. |
| `webhook_url` | no | Terminal-state POST `{job_id, status}` only — no result payload. Delivered under the §6.7 SSRF controls. In v1 (column ships with the model). |

Not exposed (D6): model choice, challenger model, `parallel_pages`, thinking budgets.

Response `202`: `{job_id, status, status_url, created_at}` (or `200` with the full result
when `timeout` was set and the job finished in time).

### 7.2 Status — `GET /agent-kv/{job_id}`

Verbose, agent-centric, stage-level:

```json
{
  "job_id": "…", "status": "running", "stage": "challenge",
  "stages": [
    {"name": "document_processing", "status": "done", "seconds": 6.2, "pages": 14},
    {"name": "extraction",          "status": "done", "seconds": 11.4},
    {"name": "qa",                  "status": "done", "seconds": 4.1,
     "keys_checked": 22, "flagged": 2},
    {"name": "challenge",           "status": "running", "fields_repulled": 1}
  ],
  "created_at": "…", "started_at": "…"
}
```

Stage list (superset; only stages that run appear): `document_processing`, `extraction`,
`qa`, `challenge`, `normalize`, `constraints`, `codegen`, `code_execution`.

### 7.3 Result — `GET /agent-kv/{job_id}/result`

The engine's full result object (§4), re-readable until `expires_at` (D11). 404 after
expiry or deletion. Failed jobs: `{success: false, error, timing}` with a user-safe error.

### 7.4 Other endpoints

- `POST /agent-kv/validate` — compile-only `keys.json` check; free; no job created;
  authenticated and rate-limited (§6.1).
- `POST /agent-kv/{job_id}/cancel` — **defined precisely** (review finding: no task
  revocation machinery exists anywhere in the platform, and none is being built):
  cancel flips the job row to CANCELLED; the terminal-state write guard (§5.4) makes
  later callbacks/stage reports no-ops; a job not yet picked up is dropped at pickup
  (executor checks job state before starting); a job mid-run **continues to completion
  in the worker** — its LLM spend is still incurred and metered, its result is
  discarded. No mid-run abort, no Celery revoke, no PG message cancellation.
- `DELETE /agent-kv/{job_id}` — delete result + any residual input immediately.
- Key management (org-scoped, session-authenticated, alongside platform key management):
  create / list / rotate / revoke `AgentKVKey`. Key storage follows the existing
  platform-key conventions (deliberate: consistent management UX per D5; hashed-at-rest
  show-once keys are a possible later hardening, not v1).

## 8. Metering and billing (D13)

Per job, corrected to the real reporting paths (review findings):

- **LLM usage** flows the way executors actually report it today: the engine accumulates
  `usage_records` in the execution result metadata; the worker flushes them via the
  usage client to the backend's internal batch endpoint (`v1/usage/batch/`) — which is
  where the transactional post-write hook seam lives, so cloud subscription/Stripe
  processing attaches unchanged. `llm_usage_reason` is a closed choice list; engine
  agents map onto it: extractor/array-extractor/QA → `extraction`, challenger →
  `challenge` (extending the enum is deferred until cloud reporting needs it).
- **Page usage** via platform-service `POST /page-usage` (fields match exactly:
  page_count, file_name/size/type, `run_id` = job id); this also fires the
  `subscription_usage` plugin. Requires the org's platform key injected into
  `executor_params` (the `PromptStudioHelper._get_platform_api_key` pattern).
- **Product attribution without an OSS schema change:** `Usage` has no product/tag
  column and gets none in v1. Attribution rides two mechanisms: `run_id` = job id joins
  usage rows to `AgentKVJob` (OSS-side aggregation), and the opaque `cloud_extras`
  payload on batch records carries `product=agent_kv` for the cloud side-tables (OSS
  forwards it verbatim, per the hook contract).

Policy (cloud-side, over meter rows; recorded here as starting suggestions only):
failed jobs bill nothing; warm-cache jobs bill page rate only. The Stripe product, its
price points, and the mapping from meters to invoice lines are cloud-repo work and out
of this document's normative scope.

## 9. Engine port notes (cloud repo)

Changes to `src/kv` in the port — the engine's extraction logic is otherwise untouched:

0. `kv_schema`/`validators` are **not ported to the cloud repo** — the engine imports
   the OSS `agent_kv` schema compiler (§5.1), keeping exactly one compiler in existence.

1. `LLMClient` construction behind an injected config (env-LiteLLM now; adapter-backed
   later, §5.2). Replace `print` debugging with structured logging.
2. `kv_cache` behind a storage backend keyed per §6.5 (object store/Redis instead of
   local disk), org-scoped.
3. `CodeExecutor.execute()` transport replaced by `CodeExecutionTransport` (§6.3); AST
   gate and JSONL validation retained.
4. LLMWhisperer credentials from platform config, not user env.
5. Stage-progress callbacks emitting to the internal status API (§5.4).
6. Cost tracking: per-agent token counts flow into `Usage` rows; env-var pricing tables
   replaced by platform pricing config.

## 10. Testing strategy

- **This repo:** serializer/compile validation (including every §6.1 cap), auth tests
  (401/404-IDOR/429/keys lifecycle), dispatch tests (`dispatch_with_callback` glue,
  enqueue-failure terminalization, `dispatched_at`, sweep), result lifecycle (TTL,
  re-read, delete, terminal-state write guard, cancel semantics, 501 plugin-absent),
  webhook SSRF guards (§6.7), usage-emission tests against a stubbed internal batch
  endpoint and platform-service.
- **Cloud repo:** engine golden tests (the existing eval harness carries over), sandbox
  integration (AST corpus, scrubbed env, limits, output caps), end-to-end job runs.
- Inherited patterns per §6.7.

## 11. Rollout

Feature-flagged (Flipt) on the cloud deployment; OSS scaffold merges dark (fails closed
without plugin, D3). Sandbox worker ships before the first flag-on. MCP (D8), batch,
webhooks-if-cut, and the enforce_type reconciliation follow as separate efforts.
