# 9e — Coupled-Pipeline Migration (Design)

**Status:** design locked, pre-implementation
**Epic:** UN-3445 (PG Queue) · **Phase:** 9e
**Predecessors:** 9a–9c (dispatch seam + PG consumer), 9d (leader-election lease + reaper / barrier-orphan sweep) — all merged.

This document defines how a **whole workflow execution** is migrated from the
legacy Celery/RabbitMQ transport to the bespoke Postgres queue, and why the
transport choice is **carried in the task payload** rather than persisted on a
shared model column.

---

## 1. The problem 9e solves

Earlier slices (9a–9c) added a `dispatch()` seam that routes a task by
**name** via `select_backend(task_name)` against the `WORKER_PG_QUEUE_ENABLED_TASKS`
allow-list. That is correct for **leaf / independent** tasks, but it cannot
migrate the execution pipeline, because the pipeline is a **coupled, multi-stage
fan-out/fan-in**:

```
async_execute_bin   →   fan-out: N × process_file_batch   →   fan-in: callback   →   destination
   (stage 1)                  (stage 2, parallel)                 (stage 3)
```

Two facts make this hard:

1. **The worker code is shared.** The same `process_file_batch` /
   orchestration code runs whether a **Celery worker** (pulled from RabbitMQ)
   or a **PG consumer** (polled from `pg_queue_message` via `SELECT … FOR UPDATE
   SKIP LOCKED`) picked the task up. The running task does **not** inherently
   know which transport it is on.

2. **Stages 2 and 3 are enqueued from inside the workers**, not by the backend.
   The worker running `async_execute_bin` is the one that must enqueue the file
   batches *and* set up the barrier/callback — so **it** has to know whether to
   use a Celery `chord` or a PG enqueue + `PgBarrier`.

> **Migration coherence rule.** An execution must run **entirely** on one
> transport, end-to-end. The migration unit is the **execution**, not the task.
> A pipeline that starts on PG must fan-out, fan-in, and recover on PG; likewise
> for Celery. Splitting a single execution across transports (e.g. a callback
> looking for a Celery chord whose counter actually lives in `pg_barrier_state`)
> is the failure mode this phase is designed to prevent.

So `select_backend(task_name)` (per-task, name-based) is **insufficient**: the
same task name must go to PG for one execution and Celery for another. We need a
**per-execution** transport decision that every stage can read.

---

## 2. Decision split: Flipt **decides**, the payload **remembers**

These are two distinct jobs and must not be conflated.

### Flipt = make the decision (once, at creation)

The rollout question — *"should this **new** execution ride PG queue?"* — is
answered **once**, at the single creation chokepoint, using the existing
`@unstract/flags` Flipt infrastructure
(`check_feature_flag_status(flag_key, entity_id, context)`):

- `entity_id` → consistent **percentage-rollout** hashing.
- `context={"organization_id": ...}` → **per-org** segment targeting.

This is the only place Flipt is consulted.

#### Flipt flag contract (fixed)

PR 3's `resolve_transport` reads this exact flag. Live rollout state (whether the
flag exists in a given env, current rollout %) is tracked in the PR / ticket, not
here — this table is just the durable contract PR 3 codes against.

| Property | Value |
|----------|-------|
| Flipt version | the `flipt` image pinned in `docker/docker-compose-dev-essentials.yaml` (single source — don't duplicate the tag here) |
| Flag type | **Boolean** (binary decision — no variant/payload needed) |
| Key | `pg_queue_execution_enabled` |
| Default value | **`false`** → legacy Celery (fails closed; returned when no rollout matches) |
| Rollouts | percentage (0%→ramp) + optional per-org segment, added in PR 3 / rollout ops |
| Helper | `check_feature_flag_status(flag_key="pg_queue_execution_enabled", entity_id=…, context={"organization_id": org_id})` → `evaluate_boolean`; already fails closed to `False` on any error / when `FLIPT_SERVICE_AVAILABLE != "true"` |
| Mapping | `True → "pg_queue"`, `False → "celery"` |
| `entity_id` (stickiness) | **TBD in PR 3** — `execution_id` (per-execution bucketing) or `organization_id` (whole orgs move together). Must be stable so an in-flight execution never re-buckets. |

Boolean (not Variant) because the choice is binary and Flipt Boolean flags
natively carry the two knobs we need: a **percentage rollout** (the canary,
sticky via `entity_id`) **plus segment rollouts** (per-org). Variant would
require Variants + Segments + Rules all configured or it returns `match=False`.

### Why Flipt cannot also be the per-stage source of truth

Three hard facts (verified against `unstract/flags/src/unstract/flags/`):

1. **The answer changes; the execution doesn't.** A percentage rollback
   (10% → 0%) or a segment edit flips Flipt's answer. But an execution already
   in flight on PG **must finish on PG**. Re-querying Flipt per stage would
   re-route a half-done execution → split-brain.
2. **Flipt fails closed to `False`.** `FliptClient.service_available` defaults
   `false`, and every error path returns `False` (`except Exception: return
   False`). A transient gRPC blip during the callback stage would silently say
   "Celery" and orphan a live PG execution. Per-stage coherence can never depend
   on a best-effort network call.
3. **The reaper has no Flipt context.** It recovers executions it did not
   dispatch; Flipt can only say "what would a *new* execution be now," never
   "what *was* this one dispatched as."

**Therefore:** evaluate Flipt once at creation → write the answer into the
**first task's payload** → never consult Flipt again for that execution.

---

## 3. Chosen design — transport carried in the task payload

The transport string (`"celery"` | `"pg_queue"`) is decided at
`create_workflow_execution` and threaded through the pipeline **in the task
payload / `ExecutionContext`** — never read from a shared DB column.

### Why payload-carry is the right home

- **It is not extra.** The shared worker code already *needs* the transport to
  pick the next-stage topology (chord vs PG+PgBarrier). Putting it in the
  payload satisfies that need directly — no separate mechanism.
- **It is durable for PG without any new column.** A PG-routed dispatch
  serialises `kwargs` into the `pg_queue_message.message` JSONB column
  (`TaskPayload`, see `pg_queue/task_payload.py`). If a worker crashes and the
  task is redelivered on visibility-timeout, the transport comes back **with the
  redelivered payload**. Recovery is covered for free.
- **The reaper needs no flag to classify executions.** The reaper only ever acts
  on **PG-specific tables** (`pg_barrier_state`, `pg_queue_message`) — presence
  there *is* "this is a PG execution." Celery executions never appear in those
  tables, so there is nothing to disambiguate. When the reaper needs the
  transport (e.g. future pipeline re-enqueue), it reads it from the payload it
  already finds in the PG row.
- **All PG-specific durable state stays in PG-specific tables.** Those tables are
  `DROP`-ped wholesale when the feature is retired. The huge, shared
  `WorkflowExecution` table is **never altered, never migrated** for this work.

### Flow

```
backend: create_workflow_execution(...)
  └─ resolve_transport(workflow, pipeline_id, org)   # Flipt, once
        → transport ∈ {"celery", "pg_queue"}
  └─ dispatch("async_execute_bin", kwargs={..., "transport": transport})
        → routed to that transport's first hop

worker: async_execute_bin   (reads transport from its own kwargs / ExecutionContext)
  └─ for each batch: dispatch("process_file_batch", kwargs={..., "transport": transport})
  └─ barrier/callback set up on the SAME transport (get_barrier honours it)

worker: process_file_batch   (transport rides in kwargs → re-stamped onward)
worker: callback             (transport in kwargs → finalises on the same transport)
```

The live worker context `WorkflowContextData`
(`workers/shared/models/execution_models.py`) gains a
`transport: str = "celery"` field, populated from the inbound task kwargs.
Default `"celery"` keeps every pre-existing payload working unchanged. In PR 1
the field is carried but **not yet re-emitted** to the stage-2/3 dispatches; the
downstream re-stamp + fan-out read land in PR 2. (Note: the unrelated
`WorkflowExecutionContext` dataclass in the same file is dead scaffolding and is
**not** the carrier.)

---

## 4. Rejected alternative — a `transport` column on `WorkflowExecution`

A persisted `WorkflowExecution.transport` column (single queryable source of
truth) was considered and **rejected** in favour of payload-carry.

**What it would have bought:** a single `WHERE transport='pg_queue'` query for
dashboards and post-completion history.

**Why rejected:**
- It touches the **shared, very large** `WorkflowExecution` table. Even though
  the change is cheap (see cost note), all of PG-queue's other durable state
  already lives in disposable PG-specific tables; adding one field to the shared
  table is the *only* migration that would outlive the feature unless explicitly
  dropped.
- The transport is **already required in the payload** for next-stage routing,
  so a column would be redundant with information we must carry anyway.
- The observability gap is small: in-flight PG executions are queryable directly
  via `pg_queue_message` / `pg_barrier_state`; historical classification comes
  from logs/metrics we already emit.

**Cost note (for the record).** The rejection is *not* on migration-cost
grounds — on Postgres 11+ both operations are cheap:
- **`ADD COLUMN`** with a nullable / constant (empty-string) default is a
  **metadata-only** catalog change — no table rewrite, near-instant regardless
  of row count (brief `ACCESS EXCLUSIVE` lock; run off-peak with a short
  `lock_timeout`).
- **`DROP COLUMN`** is likewise metadata-only (marks the column dropped, no
  rewrite).

So the column would have been operationally safe; payload-carry wins on
**design cleanliness** (no shared-table coupling, transport not duplicated, all
PG state confined to droppable PG tables), not on migration cost.

---

## 5. Deployment topology over the rollout

The payload pin classifies each in-flight execution; it does **not** remove the
need for both consumers to be live during migration. Work is delivered on two
physically separate channels:

- **Celery-pinned** executions → tasks land in **RabbitMQ** → only a **Celery
  worker** can pick them up.
- **PG-pinned** executions → tasks land in **`pg_queue_message`** → only a **PG
  consumer** (SKIP LOCKED poller) can pick them up.

| Rollout stage      | Consumers running                                              |
|--------------------|----------------------------------------------------------------|
| Today / 0%         | Celery workers only                                            |
| Canary (e.g. 10%)  | Celery workers **and** PG consumers + reaper, side by side     |
| 100% / retire      | PG consumers + reaper only; RabbitMQ + Celery workers torn down |

Both consumer sets can be **co-located in one deployment** as parallel processes
— the `pg` set (PG consumers + leader-elected singleton reaper) plus the Celery
set — which is what `run-worker.sh` already supports (`pg` / `pg-queue` set vs
the Celery sets). "One fleet, two transports in parallel," not "one loop polling
the DB."

---

## 6. Gating prerequisite — per-batch idempotency key

PG queue is **at-least-once** (visibility-timeout redelivery); the pipeline
tasks are **non-idempotent** with `max_retries=0`. Before *any* real traffic
rides PG, `process_file_batch` must carry a **per-batch idempotency key** and
guard side effects with `INSERT … ON CONFLICT (execution_id, batch_index)` so a
redelivered batch cannot double-process. This is a **hard gate** before the
canary slice, not optional hardening.

---

## 7. Slice breakdown — 3 PRs

Three PRs (each one Jira sub-task), non-regressive, dev-tested against a running
stack before any PR is opened. Ordering is forced: **PR 1 → PR 2 → PR 3** (the
seam must exist before the PG path; Flipt is pointless before the PG path
works). All land on `feat/UN-3445-pg-queue-integration`, not `main`.

> **Why 3 and not 6 or 1.** The earlier draft over-sliced. The scheduled/ETL
> path is *not* a separate PR — the chokepoint is universal (the scheduler mints
> via the same `create_workflow_execution`), so it rides PR 1 with at most one
> extra test. Rollout is *ops*, not a code PR. The idempotency key is the safety
> belt for the PG path and ships **with** it (PR 2), never separately ahead of
> it. We stop at 3 (not 1) to keep PR 1 **inert and isolated** — it merges with
> near-zero review risk and makes the branch carry `transport` everywhere, so
> PR 2 is reviewed purely as "the PG behaviour" (the highest-blast-radius code in
> the epic). Collapsing the inert seam into the risky rewire is the one merge to
> avoid.

### PR 1 — transport seam (inert, no routing change)
- `resolve_transport(...)` helper (`backend/workflow_manager/workflow_v2/
  transport.py`), **hardwired to `"celery"`** (Flipt wiring is PR 3), called at
  the two transport-emit sites: the scheduler-path HTTP view
  (`internal_api_views.py:create_workflow_execution`, returns `transport`) and
  the API/manual/async path (`workflow_helper.py:execute_workflow_async`, adds
  it to the `async_execute_bin` kwargs).
- Add `transport: str = "celery"` to the live `WorkflowContextData`
  (`workers/shared/models/execution_models.py`); populate from inbound kwargs
  (NOT `WorkflowExecutionContext`, which is dead scaffolding).
- Thread `transport` into the **stage-1** dispatch kwargs only
  (`workflow_helper.py` send + `scheduler/tasks.py` dispatch) across the entry
  paths (API / async / scheduled-ETL/TASK / manual). Stage-2 fan-out
  (`process_file_batch`) and stage-3 callback are **not** modified in PR 1 —
  they carry no `transport` yet; the downstream re-stamp + the `pg_queue` branch
  land in PR 2.
- Tests: resolver returns `"celery"`; `ExecutionContext` carries/defaults the
  field; payload round-trips the field through `to_payload`/decode; scheduled
  path carries it through.
- **Net behaviour change: none.** Pure plumbing behind a default.

### PR 2 — live PG pipeline + idempotency gate (ship together)
- Implement the `pg_queue` branch at each dispatch site: enqueue next stage via
  `dispatch()` onto PG; barrier via `get_barrier()` → `PgBarrier`.
- Fire-and-forget self-chaining (labs §5): each task enqueues the next and does
  its own in-body barrier decrement; no chord/`.link` (the PG payload carries no
  Celery `.link`).
- **Per-batch idempotency key in the same PR** — `process_file_batch` carries it;
  side effects guarded by `INSERT … ON CONFLICT (execution_id, batch_index)` so a
  vt-redelivered batch is a no-op. The PG path is never mergeable-and-enableable
  without its guard.
- Still **defaults-off** (transport still resolves to `"celery"` from PR 1).
- Dev-test end-to-end on PG via a forced `transport="pg_queue"` test workflow;
  characterisation test that a redelivered batch double-fires nothing.

### PR 3 — Flipt canary wiring (turn the knob on)
- `resolve_transport` consults Flipt (`entity_id` = execution/org for %-hashing;
  `context` = org segment), replacing the hardwired `"celery"`. Env kill-switch
  wraps it for instant rollback; Flipt fails-closed to `"celery"`.
- Reads the **fixed flag contract** in §2 (key `pg_queue_execution_enabled`,
  Boolean, default `false`). PR 3 adds the read + decides the `entity_id`
  stickiness; provisioning the flag/rollouts per env is rollout ops.

### Rollout — ops, not a PR
- Canary %, dashboards (off `pg_queue_message` / `pg_barrier_state`), runbook,
  ramp + Celery teardown criteria.

---

## 8. Key files (call-graph anchors)

| Concern                     | Location |
|-----------------------------|----------|
| Transport resolve + emit    | `workflow_v2/transport.py` (`resolve_transport`); emitted at `internal_api_views.py` (`create_workflow_execution` view → response, scheduler path) and `workflow_helper.py` (`execute_workflow_async` → `async_execute_bin` kwargs, API/manual/async path) |
| Row-builder (no transport)  | `workflow_v2/execution.py` (`WorkflowExecutionServiceHelper.create_workflow_execution` — builds the row; does NOT resolve transport) |
| Entry paths                 | API deploy, async, scheduled-ETL/TASK, manual UI — all reach one of the two emit sites above |
| Pipeline dispatch sites     | `workflow_helper.py` (stage-1 send, stage-2 batch signatures, stage-3 chord) — only stage-1 threads transport in PR 1 |
| Worker context (carrier)    | `workers/shared/models/execution_models.py` (`WorkflowContextData` — NOT the dead `WorkflowExecutionContext`) |
| Dispatch seam               | `workers/queue_backend/dispatch.py`, `routing.py` (`select_backend`) |
| PG task payload (durable)   | `workers/queue_backend/pg_queue/task_payload.py` (`TaskPayload` → `pg_queue_message.message` JSONB) |
| Barrier factory             | `workers/queue_backend/__init__.py` (`get_barrier`) |
| Barrier impls               | `barrier.py` (chord), `redis_barrier.py`, `pg_barrier.py` |
| Barrier invocation          | `workers/shared/workflow/execution/orchestration_utils.py` |
| Reaper / sweep              | `workers/queue_backend/pg_queue/reaper.py` |

---

## 9. References

- Labs architecture: `labs/workflow-execution-architecture/architecture-explorer-v2.html`
  and `labs/workflow-execution-architecture/docs/` — §5 fire-and-forget
  self-chaining is the target model for slice 3.
- 9d (merged): leader-election lease (`leader_election.py`) + reaper /
  barrier-orphan sweep (`reaper.py`).
