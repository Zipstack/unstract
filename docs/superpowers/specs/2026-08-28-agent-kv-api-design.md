# Agent-KV: Agentic Key-Value Extraction API — Design

- **Date:** 2026-08-28
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
serves status/results. Without the cloud plugin installed, dispatch fails closed at
submit time with an explicit "agent-kv engine not available on this deployment" error
(HTTP 501), mirroring the VLM plugin gating precedent.

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

### 5.3 Async dispatch rules (hard requirements, from UN-3445)

- Resolve transport **once**, at job creation, via `resolve_transport(entity_id=execution_id)`;
  carry it in the payload; never re-resolve mid-flight.
- Celery handle → `task_id` (UUID column); PG handle → `queue_message_id` (bigint column).
  Never coerce one into the other.
- Stamp `dispatched_at` positively on successful dispatch; provide a sweep for
  create-then-dispatch orphans (the 967-stuck-executions incident applies to any new
  async entry path). AgentKVJob gets its own `dispatched_at` + a periodic sweep that
  terminalizes never-dispatched jobs.
- Codegen fan-out (executor → sandbox queue) uses `queue_backend.dispatch` with the
  execution's resolved backend override.
- Logs go through `LogPublisher` (transport-agnostic).

### 5.4 Job lifecycle and state

`AgentKVJob` (new model, this repo): `id` (UUID4), `organization` FK, `api_key` FK,
`status` (PENDING → DISPATCHED → RUNNING → COMPLETED | FAILED | CANCELLED), `stage`,
`stages` (JSONB: per-stage status/timing/counters, written by the executor via the
internal API), `pages_total`, `input_ref` (object-store path), `result_ref`,
`usage_summary` (denormalized cost/tokens snapshot), `error` (user-safe message),
`dispatched_at`, `created_at`, `completed_at`, `expires_at`, `tags`, `custom_data`,
`webhook_url`.

Documents stage in org-prefixed object-store paths; queue payloads carry references,
never bytes. Results persist to the object store with a DB pointer (not Redis-only),
enabling D11 re-reads and TTL cleanup (a periodic job deletes expired results and any
leftover inputs).

Stage progress: the executor reports stage transitions through the existing internal API
pattern (workers → `/internal/v1/...`), idempotent upserts (at-least-once delivery).

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
  **local page count via pypdfium2 before OCR** vs. page cap, `keys.json` compile +
  structural caps (max leaves, array columns, nesting depth, regex length), max
  `calculations` bytes.
- Per-org concurrent-job limit (existing Redis limiter pattern) + per-key rate limit; 429.

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
  by the cloud subscription plugin's reserve/commit/discard protocol — **fail-closed**
  (viable because the engine is cloud-only).
- All cost figures measured server-side; nothing cost-related read from the request.
- Alerts: AST-gate rejection spikes, 401 bursts, repeated max-page submissions.

### 6.7 Inherited test patterns

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
| `timeout` | no | 0–300s; wait-and-return-inline if the job completes in time, else return job id (existing DX parity). |
| `tags`, `custom_data` | no | Echoed through. |
| `webhook_url` | no | Terminal-state POST `{job_id, status}` only — no result payload. First cut if notification reuse proves non-trivial. |

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

- `POST /agent-kv/validate` — compile-only `keys.json` check; free; no job created.
- `POST /agent-kv/{job_id}/cancel` — best-effort.
- `DELETE /agent-kv/{job_id}` — delete result + any residual input immediately.
- Key management (org-scoped, session-authenticated, alongside platform key management):
  create / list / rotate / revoke `AgentKVKey`.

## 8. Metering and billing (D13)

Per job, the platform writes through the existing platform-service endpoints:

- `PageUsage`: pages OCR'd (with file size/type, `run_id` = job id).
- `Usage` rows per agent call: model, prompt/completion tokens, computed USD cost,
  tagged `product=agent_kv` + job id (via the existing post-write hook seam, cloud
  attaches its subscription/Stripe processing unchanged).

Policy (cloud-side, over meter rows; recorded here as starting suggestions only):
failed jobs bill nothing; warm-cache jobs bill page rate only. The Stripe product, its
price points, and the mapping from meters to invoice lines are cloud-repo work and out
of this document's normative scope.

## 9. Engine port notes (cloud repo)

Changes to `src/kv` in the port — the engine's extraction logic is otherwise untouched:

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
  (401/404-IDOR/429/keys lifecycle), dispatch tests (transport resolution, dual handle
  columns, `dispatched_at`, sweep), result lifecycle (TTL, re-read, delete, 501
  plugin-absent), usage-emission tests against a stubbed platform-service.
- **Cloud repo:** engine golden tests (the existing eval harness carries over), sandbox
  integration (AST corpus, scrubbed env, limits, output caps), end-to-end job runs.
- Inherited patterns per §6.7.

## 11. Rollout

Feature-flagged (Flipt) on the cloud deployment; OSS scaffold merges dark (fails closed
without plugin, D3). Sandbox worker ships before the first flag-on. MCP (D8), batch,
webhooks-if-cut, and the enforce_type reconciliation follow as separate efforts.
