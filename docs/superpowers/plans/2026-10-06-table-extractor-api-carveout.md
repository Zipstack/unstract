# Table Extractor on the Agent-KV API — Standalone Release Carve-Out

**Goal:** ship `POST /agent-kv/` with `extractors: [{"name": "table", "keys": {"target_table": "…"}}]`
to customers as **its own OSS PR + cloud PR off current `main`**, excluding the
`agentic_kv` extraction engine, the schema codegen path and the hardened sandbox —
all of which stay on the large PRs ([unstract#2309](https://github.com/Zipstack/unstract/pull/2309),
[unstract-cloud#1816](https://github.com/Zipstack/unstract-cloud/pull/1816)) until those stabilise.

**Non-goal:** anything that makes the `kv` extractor reachable. This plan
deliberately leaves the KV code in the tree, dormant and tested, so the large PRs
re-enable it by reverting four one-line subtractions rather than by merging content.

**Ticket:** [UN-4232](https://zipstack.atlassian.net/browse/UN-4232), under epic [UN-4044](https://zipstack.atlassian.net/browse/UN-4044).
**Source branches to copy from:** OSS `Feat/agent-kv-api`, cloud `UN-4044-agent-kv-cloud-executor`.
**Target branches:** OSS `feat/agent-kv-api-table` off `main`; cloud `UN-4232-agent-kv-api-table` off `main`.
**Strategy: copy-forward, not cherry-pick.** The source branches carry 100+ interleaved
commits across 338 files; reconstruct the subset by copying files, then subtracting.

---

## The constraint that defines the carve-out

`workers/plugins/agentic_table/src/api_binding.py:29-32`:

```python
from agentic_kv.constants import AgentKVConfig
from agentic_kv.exceptions import PageCapExceeded
from agentic_kv.llm_adapter import build_llm, flush
from agentic_kv.progress import JobCancelled, StageReporter
```

`agentic_table/pyproject.toml` declares `unstract-agentic-table-engine` and
`unstract-extraction-seams` — **not** `agentic_kv`. The import resolves only
because both plugins are installed into the same worker image. Drop the
`agentic_kv` plugin and the table API path fails at import.

The module's own docstring already names this ("**Known debt:** … Spec step 4
moves all three behind the seams package"). So **Task 1 is spec §5 step 4,
pulled forward** — not throwaway work, just work done in the order the carve-out forces.

---

## Task 1 — Break `agentic_table`'s dependency on `agentic_kv` (cloud)

Move into `workers/plugins/extraction_seams/`, keeping **every env var name byte-identical**
so no chart, secret or external-secret wiring changes:

| New seams module | Moved from | Notes |
|---|---|---|
| `src/config.py` | `agentic_kv/src/constants.py` (`AgentKVConfig`, 248 L) | Keep the `AGENT_KV_*` env names. The table path reads `advanced_model`, `lite_model`, `llmwhisperer_api_key`, `llmwhisperer_base_url`, `parallel_pages` |
| `src/llm.py` | `agentic_kv/src/llm_adapter.py` (`build_llm`, `flush`, 502 L) + `engine/llm_client_types.py` (41 L) | `llm_client_types` holds 4 small dataclasses/exceptions; it comes along |
| `src/progress.py` | `agentic_kv/src/progress.py` (`StageReporter`, `JobCancelled`, 187 L) | **Drop `ENGINE_NODE_TO_STAGE`** — it maps KV engine nodes to KV stages and means nothing to the table path |
| `src/exceptions.py` | `agentic_kv/src/exceptions.py` (`PageCapExceeded`, `ConfigError`) | Only the two the table path raises |

Then:
- `agentic_table/src/api_binding.py` imports from `extraction_seams` — the module-scope
  seam pattern is preserved, so `tests/test_executor_api_operation.py` still patches
  `api_binding`'s own attributes; re-point the patch targets only.
- `agentic_table/pyproject.toml` is already correct — it never declared `agentic_kv`.
- `extraction_seams` keeps its one-way rule: nothing in it may import `agentic_table`,
  `agentic_table_engine` or `agentic_kv`.

**Cost to the large cloud PR on rebase:** 12 files inside `agentic_kv` import these
four modules; they re-point to `extraction_seams`. Mechanical, and it is step 4's
work regardless of this plan.

---

## Task 2 — Stand up the API app without the KV extractor (OSS)

**Copy from `Feat/agent-kv-api`:**

```
backend/agent_kv/                       (the API app; 6.5k L incl. tests)
backend/backend/{base_urls,internal_base_urls,urls_v2,settings/base}.py
backend/{pyproject.toml,sample.env,uv.lock}
unstract/filesystem/                    (the AGENT_KV storage type; 4 files)
unstract/agent-kv-schema/               (keep — see §Decision 3)
workers/ide_callback/                   (agent_kv_callback queue; 5 files)
workers/{run-worker.sh,run-worker-docker.sh,sample.env,pyproject.toml}
docker/{docker-compose.yaml,sample.env,dockerfiles/worker-unified.Dockerfile}
tests/{compose/docker-compose.test.yaml,groups.yaml}, tox.ini, pyproject.toml, uv.lock
docs/agent-kv-api.md
```

**Then subtract — four lines, each independently revertible by the large PR:**

1. **`backend/agent_kv/constants.py` — drop the `kv` entry from `EXTRACTOR_ROUTES`.**
   This is the single most important line in the carve-out. `SUPPORTED_EXTRACTORS =
   tuple(EXTRACTOR_ROUTES)` (`execution_serializers.py:33`), so one deletion makes a
   `kv` submit return **400 `unknown extractor 'kv'; supported: ['table']`**.

   Without it, a `kv` submit is accepted with a 202 and dispatched to
   `celery_executor_agentic_kv`, which has no consumer in this deployment — the job
   sits forever, durably and silently. That is the exact failure mode that already
   cost the team ~30 hours of firings with zero executions.

   **Leave `V1_EXTRACTOR_NAME`, `STAGE_NAMES`, `KVOptionsSerializer` and
   `STAGE_NAMES_BY_EXTRACTOR["kv"]` in place.** Dormant and still under test;
   `execution_views.py:45-56` already tolerates a job row naming an extractor this
   build cannot describe.

2. **`workers/run-worker.sh:76`** — remove `celery_executor_agentic_kv` from the
   executor role's queue list; same in `docker/docker-compose.yaml`.

3. **`backend/agent_kv/execution_urls.py`** — unregister the `/validate` route.
   `ValidateView` compiles a `kv` keys schema via `compile_schema`
   (`execution_views.py:255`) and nothing else; the table extractor's `keys` is
   `{"target_table": …}`, validated by `TableKeysSerializer`. Shipping an endpoint
   that validates schemas for an extractor the deployment refuses is an incoherent
   public contract. Keep the view class and the `unstract/agent-kv-schema` package —
   deleting them would force a content merge in files the large PR rewrites.

4. **Drop `workers/sandbox/`** (3 files), the `worker-sandbox` compose service and
   `PG_ROLE_SANDBOX` in `run-worker.sh`. See §Decision 2.

---

## Task 3 — Test coverage: API and end to end (OSS)

Explicit scope, not a trailing chore. The carve-out's whole claim is "this is the
stable subset", and the tests are what substantiate it. Two tiers, because they
fail for different reasons and run in different places.

### 3a · API testing — contract level, no model calls

`backend/agent_kv/tests/`, in CI on every PR, no LLM or OCR credentials. Much of
this already exists (6.5k lines, largely extractor-agnostic: auth, rate limiter,
storage, sweeps, internal views, job views) and `test_table_extractor_routing.py`
(252 L) covers the table route. Audit the submit-serializer and dispatch suites for
`kv` assumptions, then close these gaps:

| Area | Assertions |
|---|---|
| **Routing** | `SUPPORTED_EXTRACTORS == ("table",)` · a `kv` submit returns **400, not 202** |
| **Submit validation** | missing `target_table` → 400 · a `kv` option on a table entry → 400 · unknown extractor → 400 · unknown keys **or** unknown options → 400 · more than one extractor entry → 400 · oversized `extractors` payload → 400 |
| **Auth and tenancy** | no key → 403 · revoked or wrong-org key → 403 · another org's job → **404, not 403** (no existence disclosure) |
| **Limits** | per-key rate limit → 429 · concurrency cap → 429 · a cancelled job releases its slot |
| **Lifecycle** | status shape for queued / running / completed / failed / cancelled · `extractors.table.stages` non-empty and containing only `table_extraction` · result byte-for-byte stable on re-read · DELETE then GET result → 404 · swept or TTL-expired job → 404 |
| **Dispatch** | `table` routes to `("agentic_table", "table_extract_api")` · every supported extractor has a route, a stage list **and** an options serializer — the three tables stay in step |
| **Internal endpoints** | stage report · finalize · sweep · TTL cleanup, including the cleanup-failure path |
| **Webhook** | delivered once on completion · a delivery failure does not change job state |
| **Subscription gate** | expired trial and inactive subscription both 402, byte-identical to the API-deployment path · a database error surfaces as 500, never as unmetered access |

The routing row matters most. It is the guard on Task 2's first subtraction, and the
only thing standing between a future rebase and a `kv` submit that returns 202 and
then sits in an unconsumed queue forever.

The unknown-keys/unknown-options row is not padding either: DRF silently discards
unrecognised keys, so `"Options"` for `"options"` would be dropped whole, `options`
would default to `{}`, and the job would run with roughly double the LLM spend the
caller asked for — with a 202 and no indication anything was ignored.

### 3b · End-to-end testing — deployed stack, real LLM and OCR

`tests/e2e/agent_kv/`, run first against compose, then against the dev namespace
(Task 5b). These are the tests that catch the wiring failures nobody has had a
chance to hit yet.

| Scenario | What it proves |
|---|---|
| **Table happy path** — `rent_roll.pdf` | submit → poll → rows match the known table |
| **Excel path** — `invoice.xlsx` | the engine's own Excel branch extracts, and UN-4219's post-OCR cap applies |
| **Cancel mid-run** | the run stops, billing stops, the concurrency slot is released |
| **Page cap** | an oversized document is rejected before spend |
| **Sync-wait submit** | the result comes back inline |
| **Webhook on completion** | delivered with the right payload |
| **Unreadable PDF** | 400 at submit |
| **Metering** | page usage on the standard `Audit()` path, token and cost sums in `usage_summary` — the same trail as the IDE path |
| **Stages non-empty** | `GET /agent-kv/{job}` returns `stages: [{"name": "table_extraction", …}]` |

That last row is load-bearing: it is the only check that catches Task 5a's cross-repo
constant drift **from the outside** — from a client's point of view, where the
symptom is a job that completes normally while reporting no progress at all.

### 3c · Re-pointing the existing scenarios

| Keep, re-pointed to `table_keys()` | Drop (KV-engine specific) |
|---|---|
| `test_submit_without_key_is_403` | `test_validate_good_and_bad_schema` (route unregistered) |
| `test_cancel_mid_run` | `test_happy_path_extraction` |
| `test_cancelled_job_does_not_leak_its_concurrency_slot` | `test_calculation_happy_path` |
| `test_delete_completed_job_then_result_404` | `test_hostile_calculation_fails_user_safely` |
| `test_page_cap_rejects_oversized_document` | `test_resubmit_same_document_hits_document_cache` (KV's cached `DocumentProcessor`; the table path is uncached until spec step 5) |
| `test_sync_wait_submit_returns_result_inline` | `test_bad_llm_key_ends_failed` (re-point if cheap) |
| `test_webhook_delivered_on_completion` | |
| `test_concurrency_limit_returns_429` | |
| `test_submit_unreadable_pdf_is_400` | |
| `test_excel_submit_extracts` — **keep, re-pointed.** The table engine has its own Excel branch and UN-4219's post-OCR page cap applies there | |

Already table-native, keep as-is: `test_table_extractor_happy_path`,
`test_table_entry_without_a_target_table_is_400`, `test_a_kv_option_on_a_table_entry_is_400`,
`test_an_unknown_extractor_is_400`.

Fixtures: keep `rent_roll.pdf` and `invoice.xlsx`; `invoice.pdf` only if a re-pointed
scenario still uses it.

### 3d · Where each tier runs

- **3a** — the unit and integration groups in `tests/groups.yaml`, every PR, no credentials.
- **3b** — the e2e group against compose on the PR, and against the dev namespace once
  deployed (Task 5b). Gate the model-calling scenarios on the existing `require_llm`
  fixture so a credential-less run skips rather than fails.
- **Cloud** — `tests/groups.cloud.yaml` carries `agentic_table`, `agentic_table_engine`
  and `extraction_seams`. These go **red by design** until the OSS PR lands, exactly as
  the `agentic_kv` groups do today. Say so in the PR description so a reviewer does not
  read it as breakage.

---

## Task 4 — The cloud half, minus the engine and the sandbox

**Include:**

```
workers/plugins/agentic_table/          (9 files)
workers/plugins/agentic_table_engine/   (77 files)
workers/plugins/extraction_seams/       (5 files + Task 1's four new modules)
backend/plugins/agent_kv/               (5 files — the subscription gate)
charts/unstract-platform/templates/shared/agent-kv-secret.yaml
charts/unstract-platform/templates/shared/storage-secret.yaml
charts/unstract-platform/templates/backend/agent-kv-cronjobs.yaml
charts/unstract-platform/templates/external-secrets/external-secrets.yaml
charts/unstract-platform/templates/_helpers.tpl
charts/unstract-platform/templates/worker-v2/configmaps-specific.yaml
charts/unstract-platform/{values.yaml,unittests/agent_kv_cronjobs_test.yaml,
  unittests/agent_kv_wiring_test.yaml,unittests/pg_worker_fleet_test.yaml,
  unittests/render_guards_test.yaml}
charts/cloud-deployment-values/cloud.values.yaml
tests/groups.cloud.yaml, copy_cloud_deps.py (+ its test), .github/workflows/…
```

**Exclude:** all 97 `workers/plugins/agentic_kv/` files · `charts/unstract-platform/templates/worker-sandbox/` (5 files) · `unittests/sandbox_wiring_test.yaml` · `unittests/agent_kv_calculations_ga_test.yaml`.

**Chart edits, not deletions:**
- `values.yaml` keeps the whole `AGENT_KV_*` block — the table path reads the same
  env through Task 1's seams config — but drops the `agentic_kv` executor fleet entry
  and the sandbox fleet.
- **`pg_worker_fleet_test.yaml` must be edited to assert the fleet actually shipped.**
  Left untouched it either fails the build or, worse, passes while guarding a fleet
  that no longer exists. The guard is the only thing standing between this deployment
  and an unconsumed queue; a guard that guards nothing is worse than no guard.
- `agent_kv_wiring_test.yaml`: the `AKV-Q5` assertion on
  `celery_executor_agentic_kv` comes out with the fleet entry.

No new worker fleet is needed: `celery_executor_agentic_table` is already wired in
production for the IDE table path, which is precisely why the table work chose a
second *operation* over a new executor name (plan ruling R1).

---

## Task 5 — The cross-repo constant, and a real deploy

**5a. Pin the silent-drift constant.** `STAGE_TABLE_EXTRACTION = "table_extraction"`
(cloud `api_binding.py`) must equal `TABLE_STAGE_NAMES[0]` (OSS
`backend/agent_kv/constants.py:41`). Today **only a pair of comments ties them**.
On drift: `StageReportView` persists whatever the executor sends, `_status_document`
filters it through the OSS list, and every status response returns an empty `stages`
array while jobs complete normally. No test on either side can catch it alone.

For a first customer-facing release this is the bug that reads as "your API is
broken". Cheapest fix: assert the literal on both sides, each test naming the other
repo's file and value, so a change to one fails the other's suite on the next sync.

**5b. Deploy and exercise it.** Push to the dev namespace and run the table e2e
against the deployed stack. The PG consumer wiring and the agent-kv CronJobs have
never run outside compose ([UN-4213](https://zipstack.atlassian.net/browse/UN-4213)).
Dropping the sandbox removes the hardest half of that validation — no hardened pod,
no NetworkPolicy, no least-privilege DB role to prove out.

**Exit criteria for the whole carve-out:**
- a `table` submit against the deployed stack returns rows for `rent_roll.pdf`
- `GET /agent-kv/{job}` reports a non-empty `stages: [{"name": "table_extraction", …}]`
- a `kv` submit returns 400, not 202
- cancel mid-run stops the run and releases the concurrency slot
- the xlsx path extracts and is capped
- page usage and token/cost land on the usual `Audit()` path
- the full API suite (§3a) is green in CI without credentials
- `helm unittest` green with the reduced fleet, and `pg_worker_fleet_test`
  demonstrably **fails** when a fleet entry is removed
- OSS PR merged before the cloud PR — the cloud table groups depend on the OSS routing

---

## Task 6 — Documentation and the public contract

- `docs/agent-kv-api.md:199` currently reads "Which extractor: `kv` or `table`".
  It must say `table` is the only supported value on this deployment, and the
  `/validate` section comes out with the route.
- Customer-facing docs in `unstract-docs` (Docusaurus).
- The `202` → poll `GET /{job}` → `GET /{job}/result` flow, the `target_table`
  parameter, the `extractors.table` result shape, and the webhook.

---

## Decisions

**1 · Quota admission — deferred. Decided 2026-10-06.**
The entitlement gate ships: `backend/plugins/agent_kv/service.py` calls the same
`get_subscription` / `verify_subscription` the API-deployment middleware calls, so an
expired trial or inactive subscription gets a byte-identical 402. What is **not**
wired is quota — an org inside a valid subscription but over its page or token
allowance runs and bills anyway ([UN-4216](https://zipstack.atlassian.net/browse/UN-4216),
tagged a GA blocker). This release ships without it; revisit before open availability.

**2 · The sandbox is excluded — decided 2026-10-06. Ship what exists.**
`agentic_table` generates Python with an LLM and executes it on **every run**
(`runner.py:1158`, `1340`) through its own `code_executor.py`, where an AST gate
blocking four builtins is the entire boundary: no rlimits, no isolated pod, no
NetworkPolicy. That pod holds LLM keys, OCR adapters and storage credentials and has
full egress. **This is exactly what the IDE table path does in production today**, so
the carve-out introduces no new class of risk — but it does widen reach from
"Prompt Studio users in the org" to "any holder of an API key".
Shipping as-is, with [UN-4215](https://zipstack.atlassian.net/browse/UN-4215) as the
immediate fast-follow rather than a backlog item. Pulling the sandbox in now
would also force the module-allowlist reconciliation (the table prompt permits 15
modules, the gate allows 10; `copy`, `pathlib`, `string`, `textwrap`, `time`,
`unicodedata` are rejected) — which is the thing most likely to destabilise the
table path, i.e. the opposite of what this carve-out is for.

**3 · Keep `unstract/agent-kv-schema` and `ValidateView`, unregister the route.**
The package is zero-dependency, self-contained and fully tested, and
`execution_serializers.py` imports `compile_schema` at module scope. Deleting it
forces a content merge in the file the large PR rewrites most; keeping it costs
twelve dormant files and leaves the large PR a one-line route restoration.

**4 · Keep the URL `/agent-kv/`.** It reads oddly for a table-only API, but the first
customers' integrations are the thing a later rename breaks. Name it the agentic
extraction API in the docs and leave the path alone.

**5 · One extractor per job stays.** `execution_serializers.py:283` rejects more than
one entry. That is exactly right for table and needs no work here.

---

## Risks

| Risk | Why it bites | Mitigation |
|---|---|---|
| Rebase cost on the large PRs | The carve-out touches `constants.py`, `execution_serializers.py`, `execution_urls.py`, `run-worker.sh`, `values.yaml` — files both large PRs own | Every subtraction is the deletion of a line whose code still exists. The large PRs re-add four lines and re-point 12 imports; no content merge |
| Temporary duplication in `extraction_seams` | Task 1 moves four modules out of `agentic_kv`, which the large cloud PR still carries copies of | Expected and bounded: the large PR's rebase re-points its 12 importers, completing spec §5 step 4 |
| A helm guard edited into uselessness | `pg_worker_fleet_test` is the only thing catching an unconsumed queue | Edit the assertions to the shipped fleet and verify the test **fails** when a fleet entry is removed |
| Uncached OCR on the table API path | Ruling R3: one LLMWhisperer pass per run until spec step 5 / [UN-4096](https://zipstack.atlassian.net/browse/UN-4096) | Cost, not correctness. Size it against expected customer volume before launch |
| Table reports one coarse stage | The engine has no node-level hooks, so `stages` is `["table_extraction"]` | Known and documented; do not invent stage names the executor cannot substantiate |

---

## Sequencing

Task 1 gates Task 4 (the cloud PR cannot build without it). Tasks 2 and 3 are OSS and
run in parallel with Task 1. Task 4 needs Task 1; Task 5 needs both PRs stood up;
Task 6 runs alongside from the start. OSS merges before cloud — the cloud table test
groups depend on the OSS routing.

No week numbers: size this on a walkthrough. The honest shape is that Task 1 is the
only genuinely new engineering, Tasks 2–4 are subtraction and re-wiring of code that
already exists and already passes, and Task 5b is the validation nobody has done yet
for any of it.
