# Agent-KV — Architecture Overview & Handover Index

**Status:** built, reviewed, and proven end-to-end on docker-compose (real-HTTP curl,
2026-09-02). Not yet deployed to Kubernetes — see [§7 Current status](#7-current-status).

This is the one-page map of the Agent-KV feature: what it is, how a request flows through
it, which pieces live in which repo, the security model in brief, and pointers into the
six detailed documents. Read this first, then follow the links in [§8](#8-document-index)
for depth.

---

## 1. What Agent-KV is

A metered, async HTTP API that extracts structured key-value and tabular data from an
uploaded document against a caller-supplied schema (`keys.json`), optionally running
engine-generated **calculations** over the extracted rows. It productizes the KV extractor
from the `unstract-agentic-table` research project as a first-class Unstract API.

- **Public surface:** `POST /agent-kv/` (submit) and sibling status/result/cancel/validate
  endpoints, authenticated by a per-organization `AgentKVKey` (a UUID, `Authorization:
  Bearer <key>`). Full contract in [`docs/agent-kv-api.md`](agent-kv-api.md).
- **Async:** submit returns a `job_id`; the caller polls status or receives a webhook.
- **Metered:** LLM tokens and OCR pages are recorded server-side per job; spend is bounded
  before dispatch and admission is fail-closed (cloud subscription plugin).

## 2. One system, two repositories

Agent-KV is deliberately split so the OSS half is fully functional scaffolding and the
paid engine is a cloud plugin.

| Repo | Branch | Holds |
|---|---|---|
| **OSS** `Zipstack/unstract` | `Feat/agent-kv-api` | The API app, job lifecycle, schema compiler, dispatch glue, callbacks, and the **hardened sandbox worker** (generic infra). |
| **Cloud** `unstract-cloud` | `UN-4044-agent-kv-cloud-executor` | The `agentic_kv` executor plugin (the ported extraction engine + LLM/OCR clients), the sandbox transport, the capability marker, and all chart/deploy wiring. Jira **UN-4044**. |

**Fail-closed by design:** the OSS backend cannot see the executor plugin registry (that
lives in the workers process). A backend-visible capability marker
(`backend/plugins/agent_kv`, cloud) is probed with `get_plugin("agent_kv")`; when it is
absent (OSS-only deployment) submit returns **HTTP 501** instead of enqueuing to a queue
no worker consumes.

## 3. End-to-end request lifecycle

```
  client
    │  POST /agent-kv/  (file + keys.json + options[+calculations])   Bearer <AgentKVKey>
    ▼
┌─ OSS: agent_kv Django app ────────────────────────────────────────────────┐
│  auth (view-owned) · validate + compile keys.json · file/page/size caps    │
│  create AgentKVJob · stage input to object store (refs, never bytes)        │
│  concurrency slot · dispatch_with_callback(executor_name="agentic_kv")      │
└───────────────┬────────────────────────────────────────────────────────────┘
                │ queue: celery_executor_agentic_kv        (501 here if engine absent)
                ▼
┌─ CLOUD: agentic_kv executor plugin (worker-executor fleet) ────────────────┐
│  read input · OCR (LLMWhisperer + doc cache + page usage)                   │
│  LLM extraction stages (key/array/QA/challenger) · normalize · score        │
│  if calculations: generate code, then hand off ──────────┐                  │
└──────────────────────────────────────────────────────────┼─────────────────┘
                                                            │ request-reply,
                                                            │ queue: sandbox_codegen
                                                            ▼
                              ┌─ OSS: sandbox worker (isolated, hardened) ────┐
                              │  AST gate · scrubbed-env subprocess · rlimits │
                              │  sees ONLY {record JSON + code}; no doc,      │
                              │  no schema, no tenant id, no secrets, no net  │
                              │  → rows_jsonl (validated, capped)             │
                              └──────────────────────┬────────────────────────┘
                                                     │ reply
                ┌────────────────────────────────────┘
                ▼
┌─ OSS callback (agent_kv_callback queue) ───────────────────────────────────┐
│  finalize: persist result · delete staged input · release slot · webhook   │
│  write usage_summary (tokens/pages/cost)                                    │
└───────────────┬────────────────────────────────────────────────────────────┘
                ▼
  client  ── GET /agent-kv/{job_id}          → status (PENDING→DISPATCHED→RUNNING→terminal)
          ── GET /agent-kv/{job_id}/result   → record + calculation_rows + usage
```

Stage transitions are reported by the executor through the internal API
(`/internal/v1/agent-kv/...`, idempotent, at-least-once). Two periodic jobs — a
never-dispatched **sweep** and a TTL **cleanup** (expired results + leftover inputs) — run
as internal endpoints driven by the PG scheduler (cloud: two CronJobs).

## 4. Component map

### OSS (`Feat/agent-kv-api`)
| Path | Responsibility |
|---|---|
| `backend/agent_kv/` | Django app: `AgentKVKey`/`AgentKVJob` models, public execution views + urls, serializers, dispatch, callbacks, results persistence + TTL, usage emission, internal + key-management APIs. |
| `unstract/agent-kv-schema/` | The `keys.json` schema compiler (`unstract.agent_kv_schema`) — **single source of truth**, imported by the cloud engine so validation and execution cannot drift. Enforces structural caps and the depth ceiling. |
| `workers/sandbox/` | `WorkerType.SANDBOX`: the `execute_sandboxed_code` task, the AST gate (normative copy), and `runner.py` (scrubbed-env subprocess + rlimits + output discipline). |
| `docs/agent-kv-api.md` | The API/operator reference (auth, endpoints + curl, webhooks, retention, deploy checklist §12, env reference §13). |

### Cloud (`UN-4044-agent-kv-cloud-executor`)
| Path | Responsibility |
|---|---|
| `workers/plugins/agentic_kv/src/executor.py` | `AgenticKVExecutor` — validates params, reads input, builds LLM/OCR clients, runs the engine, maps the result. Registered via entry point `agentic_kv`. |
| `workers/plugins/agentic_kv/src/engine/` | The ported `src/kv` extraction engine (extractors, QA, challenger, codegen, normalizers, scorer). Imports the OSS schema compiler. |
| `workers/plugins/agentic_kv/src/sandbox_transport.py`, `code_transport.py` | `SandboxCodeTransport` (request-reply to `sandbox_codegen`) + the `CodeExecutionTransport` ABC and the fail-closed `UnavailableCodeTransport` default. |
| `backend/plugins/agent_kv/` | The capability marker (`metadata["name"]=="agent_kv"`) that makes OSS `get_plugin("agent_kv")` truthy. |
| `charts/unstract-platform/templates/worker-sandbox/` | The sandbox Deployment, NetworkPolicy, PDB, and minimal Secret. Plus queue/env wiring for the executor + callback fleets. |

## 5. Security model in brief

Premise: **the document, `keys.json`, `key_notes`, and `calculations` are all
attacker-controlled**, and they flow into prompts and generated code. The full model is
[design §6](superpowers/specs/2026-08-28-agent-kv-api-design.md); the codegen sandbox is
the load-bearing control.

**The sandbox's five layers** (all enforced server-side in `workers/sandbox/`, never
trusting the client):
1. Fail-closed **AST gate** (import allowlist + denylisted calls/attrs/dunders).
2. **Scrubbed-env subprocess** — empty environment, minimal PATH, per-request tempdir,
   `-I -S -E`, `start_new_session`, rlimits (CPU/mem/NPROC/NOFILE/FSIZE), process-group
   kill at `timeout + grace`.
3. **Hardened pod** — non-root, read-only rootfs + `emptyDir` /tmp, all caps dropped,
   `seccompProfile: RuntimeDefault`, no service-account token, CPU/mem/PID limits.
4. **NetworkPolicy** — default-deny ingress+egress; egress only to broker, Postgres, DNS.
   No object store, no platform-service, no backend, no internet.
5. **No secrets** in the pod beyond its own broker/result-backend DB credential — and
   critically **not** the platform master `ENCRYPTION_KEY`.

The sandbox receives only `{record JSON + generated code}` — no document, no schema, no
tenant identifiers; output is validated JSONL, row- and byte-capped.

**Accepted v1 residual (R12):** generated code legitimately needs `open()`/`pathlib`, so
it can read a world-readable file *in its own pod* and return it to the submitting
customer. Contained by layers 2–5 (no secrets, non-root read-only rootfs, no egress,
per-job tempdir, results only to the caller's own key) → worst case is disclosure of a
**non-sensitive** container file to the caller who submitted the job. This is why the
default-deny egress and no-secrets invariants are load-bearing and must not be relaxed.
Deferred mitigation: `runtimeClass: gvisor`. Full analysis in
[sandbox design §8a](superpowers/specs/2026-09-01-agent-kv-sandbox-worker-design.md).

Other boundaries: view-owned auth with per-endpoint 401 tests; UUID4 job ids + org-scoped
lookups (IDOR → 404); webhook SSRF controls (private/link-local/metadata ranges refused,
re-checked at connect time, no redirects, `{job_id, status}` body only); org-scoped cache
key (cross-tenant reuse structurally impossible); fail-closed billing admission.

## 6. Runtime & configuration essentials

- **Sandbox image (v1):** runs from the existing `worker-unified` image with command
  `sandbox` (a dedicated stdlib-only slim image is a deferred upgrade). The security
  guarantees come from the scrubbed subprocess + pod hardening, not image contents.
- **`calculations` GA flag:** `AGENT_KV_CALCULATIONS_ENABLED=true`. Off degrades cleanly
  (submit rejects `calculations`; nothing dispatches mid-pipeline).
- **Object storage:** `FileStorageType.AGENT_KV`, org-rooted at
  `{AGENT_KV_STORAGE_DIR_PREFIX}/{org_id}/{job_id}/` (default prefix `unstract/agent_kv`);
  the first path segment is the bucket — backend and executor **must** share the value.
- **Celery result backend (`CELERY_BACKEND_DB_*`):** required for the sandbox request-reply
  path. Cloud supplies it via the chart secret; dev must set it (the compose rig wires it
  to Postgres).
- Full env matrix: [`docs/agent-kv-api.md` §13](agent-kv-api.md); deploy order and the
  chart's four hard-coded storage-secret sites: [§12](agent-kv-api.md).

## 7. Current status

- **Built & reviewed:** both sub-projects complete; a pre-Greptile review fixed 5 Critical
  + ~18 Important findings (gate bypasses, schema depth/recursion DoS, a finalize
  data-loss race, a slot leak, status casing, engine array-drop, model-ID defaults).
- **Proven live (docker-compose, real-HTTP curl, 2026-09-02):** submit → poll → result
  with array rows preserved and a calculation computed out-of-process
  (`line_count: 3, amount_total: "482.50"`); `calculations_applied: true`,
  `execution.success: true`; sandbox held read-only rootfs with 0 restarts; auth negatives
  (no key / bad key → 403); schema-DoS guard (600-deep schema → `200 valid:false "exceeds
  max_depth=6"`, zero 500s). Reproduce with the scratch `curl-smoke.sh` recipe.
- **Not yet validated:** a real **Kubernetes** deploy. The chart, the NetworkPolicy-based
  sandbox containment, the minimal Secret, and the sandbox result-backend wiring are
  helm-unittest-rendered but never applied to a cluster. **This is the one outstanding
  validation before production.**
- **Branch state:** all fix commits (plus this overview) are **committed and pushed** on
  both branches — OSS `Feat/agent-kv-api`, cloud `UN-4044-agent-kv-cloud-executor`;
  **no PR raised yet** (both must pass Greptile first).
- **Not started:** the fail-closed billing admission gate + Stripe invoicing (see
  **Billing & metering** below); migrating `agentic_table` onto this shared sandbox.

### Billing & metering

**Usage recording — built and wired** (rides the platform's standard usage pipeline):
- **LLM token/cost usage:** the executor flushes each LLM's pending usage exactly-once into
  `metadata.usage_records`; the generic executor task harvests them →
  `usage_client.bulk_create_usage(...)` → `POST v1/usage/batch/`.
- **OCR page usage:** `PageUsagePoster` → `Audit().push_page_usage_data(...)`
  (platform-service), which fires the subscription hook — the same path
  `unstract.sdk1.x2txt.X2Text` uses.
- **Per-job snapshot:** `usage_summary = {pages, input_tokens, output_tokens, total_cost,
  agents}` stored on `AgentKVJob`; `total_cost` is the authoritative billing figure.
- **Status:** unit-tested and runs whenever a job completes; asserting a `usage_v2` row
  end-to-end is a staging check (not separately asserted in the compose run).

**Not built — deferred to the billing sub-project:**
- **Fail-closed pre-dispatch admission / quota reserve** (design §6.6): submit today gates
  on capability (501), per-key rate (429), schema caps, and concurrency (429) — but **not**
  a billing quota reservation. A job can run and record usage even if the org is over
  quota; enforcement is deferred.
- **Stripe / invoicing** (billing sub-project): not started — turning recorded usage into
  charges.

## 8. Document index

**Operator / integrator**
- [`docs/agent-kv-api.md`](agent-kv-api.md) — API reference: auth, schema format, every
  endpoint with curl, webhooks, retention, 501 behavior, **deploy checklist (§12)**,
  **environment reference (§13)**.

**Architecture / design (one per sub-project)**
- [`docs/superpowers/specs/2026-08-28-agent-kv-api-design.md`](superpowers/specs/2026-08-28-agent-kv-api-design.md)
  — the API/job layer: architecture, security model, API contract, metering, rollout.
- [`docs/superpowers/specs/2026-09-01-agent-kv-sandbox-worker-design.md`](superpowers/specs/2026-09-01-agent-kv-sandbox-worker-design.md)
  — the codegen sandbox worker: placement, transport, task contract, hardening, R12.
- `unstract-cloud: docs/superpowers/specs/2026-08-29-agent-kv-cloud-executor-design.md`
  — the cloud executor plugin + engine port: components, data flow, engine-port map,
  chart wiring. *(Lives in the cloud repo.)*

**Implementation plans (task-by-task)**
- OSS: `docs/superpowers/plans/2026-08-28-agent-kv-oss-half.md`,
  `docs/superpowers/plans/2026-09-01-agent-kv-sandbox-worker.md`
- Cloud: `docs/superpowers/plans/2026-08-29-agent-kv-cloud-executor.md`

## 9. Recommended next steps for the architect

1. Review both branches, then push and open the PRs (they need to pass Greptile).
2. Deploy the cloud branch to **staging** — this is the missing validation: confirm the
   sandbox Deployment comes up hardened, the NetworkPolicy actually blocks egress, the
   result-backend wiring works, and a live `calculations` job completes.
3. Decide on the R12 residual: ship v1 with the layer-2–5 containment as documented, or
   pull the `runtimeClass: gvisor` mitigation forward.
