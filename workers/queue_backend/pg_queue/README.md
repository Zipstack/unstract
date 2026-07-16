# PG Queue — Reference & Glossary

A quick-reference dictionary for the bespoke Postgres-backed work queue that can
stand in for Celery/RabbitMQ. This file is the **terminology + config lookup**.

The transport is chosen **per org** by the Flipt flag `pg_queue_enabled`
(fail-closed to Celery), so the system runs **with and without** PG unchanged.

---

## 1. Configuration — quick reference

All knobs are environment variables. Consumer knobs are read via
`consumer_env("<SUFFIX>", …)` → `WORKER_PG_QUEUE_CONSUMER_<SUFFIX>`. Authoritative
defaults live in the code constants (`consumer.py`, `pg_queue_consumer/supervisor.py`,
`reaper.py`); cloud overrides live in the Helm chart `values.yaml`.

**Units:** every duration is in **seconds**, and the **Default column shows the raw
value you set** — a plain number, e.g. `30` means 30 seconds (set `…=30`, not `30s`).
The `*_SECONDS` suffix names the unit; `POLL_INTERVAL` and `BACKOFF_MAX` are also
seconds (floats allowed). Counts (`CONCURRENCY`, `BATCH`, `MAX_ATTEMPTS`) are plain
integers.

### Consumer (`WORKER_PG_QUEUE_CONSUMER_*`)
| Env suffix | One-line | Default |
|---|---|---|
| `CONCURRENCY` | Prefork consumer children per pod (1 = plain single process) | `1` |
| `VT_SECONDS` | The **drain / max-runtime bound** (drives `SHUTDOWN_GRACE`, `HEALTH_STALE`, the chart guards) — the *claim* window is `LEASE_SECONDS`, not this | `30` (chart: `9060` for file-processing ≈ 2.5h) |
| `LEASE_SECONDS` | **Renewable claim window** — the effective claim window is `min(LEASE, VT)`, renewed every ~that/3 while the task runs; a dead worker's claim expires in ~that → fast redelivery. With the defaults (`LEASE=120`, `VT=30`) it clamps to 30; the chart raises VT so the full 120 applies | `120` |
| `SHUTDOWN_GRACE_SECONDS` | Graceful-drain budget (shared across all children) on SIGTERM before SIGKILL | `= VT` (floored at `30`) |
| `QUEUE` | Queue name(s) this consumer polls (comma-separated) | `default` |
| `BATCH` | Messages claimed per poll | `1` |
| `POLL_INTERVAL` | Time between polls when the queue is empty | `0.1` |
| `BACKOFF_MAX` | Max empty-queue poll backoff | `2.0` |
| `MAX_ATTEMPTS` | Max deliveries before a message is dropped as **poison** | `5` |
| `HEALTH_PORT` | Liveness HTTP port (unset → probe disabled) | unset |
| `HEALTH_STALE_SECONDS` | A poll loop idle beyond this is reported unhealthy | `60` |
| `WORKER_TYPE` | Which source worker's tasks this consumer registers (bootstrap) | — |

### Reaper (`WORKER_PG_REAPER_*`)
| Env | One-line | Default |
|---|---|---|
| `INTERVAL_SECONDS` | Reaper cycle cadence (stuck-batch / orphan detection) | `5` |
| `SWEEP_SECONDS` | Retention-sweep cadence (expired `pg_task_result`, etc.) | `300` (5 min) |
| `HEALTH_PORT` / `HEALTH_STALE_SECONDS` | Reaper liveness probe | stale `30` |

### Orchestration / barrier / connection
| Env | One-line |
|---|---|
| `WORKER_PG_BATCH_STUCK_TIMEOUT_SECONDS` | A barrier whose `last_progress_at` hasn't advanced this long is fast-failed by the reaper |
| `WORKER_PG_ORCHESTRATOR_LEASE_SECONDS` | Leader-election lease duration for the single-orchestrator role |
| `WORKER_PG_DEDUP_RETENTION_SECONDS` | Retention for `pg_batch_dedup` rows |
| `WORKER_PG_QUEUE_CONNECT_RETRIES` / `_BACKOFF` | Reconnect attempts / backoff on a stale or broken DB connection |

### Routing / flag
| Env / flag | One-line |
|---|---|
| `pg_queue_enabled` (Flipt, `PG_QUEUE_FLAG_KEY`) | Per-org gate that routes dispatch to PG; **fail-closed to Celery** on any Flipt error |
| `WORKER_PG_QUEUE_ENABLED_TASKS` | Comma-separated task names eligible for PG routing (empty → everything stays on Celery) |

---

## 2. Concepts — glossary

**Visibility timeout (VT)** — when a consumer *claims* a message it becomes invisible
to other consumers until its `vt` passes. If the worker finishes and deletes (acks) it,
it's gone; if the worker dies without acking, the `vt` expires and the message
**redelivers**. There's no live broker connection like RabbitMQ, so the `vt` is the
queue's only "worker died" signal — recovery latency ≈ how far out the `vt` is.

**Renewable lease (`LEASE_SECONDS`)** — rather than claim for the full `VT`
(up to 2.5h), the consumer claims for a **short** `LEASE` and a background thread
**renews** it (`set_vt`) every ~`LEASE/3` while the task runs. A live-but-slow task
keeps its claim; a **dead** worker's renewal stops, so its `vt` expires in ~`LEASE` →
redelivery in **minutes, not hours**. `VT_SECONDS` is retained as the *drain /
max-runtime bound* (grace, health-stale), and the lease is clamped to it. Note the
lease is **not** a hard cap on runtime — a live-but-hung task keeps renewing forever;
the backstop for that is the liveness probe restarting the pod (process death stops
renewal). The renewal owns its own DB connection (closed on exit) and is best-effort:
a connection death retries within the `~2×` slack the `LEASE/3` interval leaves before
expiry, and escalates to an ERROR log once it keeps failing past `LEASE` (the lease is
then genuinely lost and the message may double-run). Because renewal covers only the
in-flight message, `BATCH_SIZE` is forced to 1 whenever the lease is the short window.

**Claim** — an atomic `SELECT … FOR UPDATE SKIP LOCKED` that hides up to `BATCH`
ready rows for the claim window (`min(LEASE, VT)`) and hands them to one consumer.
`SKIP LOCKED` distributes work across children and replicas without contention.

**Redelivery / at-least-once** — a message can be delivered more than once (VT expiry
after a crash, or a poison re-park). Handlers must tolerate re-execution.

**Near-exactly-once** — writes to an *external* system (e.g. a customer destination
DB) can't be transactional with our Postgres markers, so a crash in the tiny
write→mark gap can duplicate. Guards (FileHistory, etc.) reduce this to a narrow
window, but it isn't strictly exactly-once.

**Poison message / re-park** — a message that fails `MAX_ATTEMPTS` times. Rather than
redeliver forever it is dropped (or re-parked with `POISON_REPARK_VT_SECONDS`, bounded
by a budget) so a permanently-bad row can't wedge the queue.

**Prefork supervisor / fleet** — `WORKER_PG_QUEUE_CONSUMER_CONCURRENCY > 1` forks N
isolated consumer child processes (the PG analogue of Celery `--pool=prefork
--concurrency=N`). The *supervisor* owns the liveness port, re-forks crashed children
(rate-limited), and drains them on shutdown. The *fleet* is the set of children.

**Shutdown grace** — on SIGTERM the supervisor waits up to `SHUTDOWN_GRACE_SECONDS`
(= VT) for children to finish their in-flight batch, using a **single shared
deadline**, then SIGKILLs stragglers. Must be ≤ the pod's
`terminationGracePeriodSeconds` (the chart sets `grace = VT + buffer`).

**Liveness / heartbeat** — each child stamps its last-poll time into a shared array;
the supervisor reports the *oldest* child's staleness on `/health`. Frozen during a
long task, so a wedged child goes stale and trips the probe.

**Reaper** — a singleton (leader-elected) sweeper that recovers **stranded** work:
fast-fails a barrier whose `last_progress_at` stalled, cascades a terminal
execution to its files, and sweeps expired retention rows.

**Barrier (`PgBarrierState`)** — the fan-in counter for a batched execution: each
file-batch decrements `remaining`; when it hits 0 the aggregating callback fires. It
carries `last_progress_at` (the reaper's liveness signal for stuck detection).

**`last_progress_at`** — timestamp bumped whenever a batch makes progress.
Lets the reaper fast-fail a stalled batch in ~stuck-timeout instead of the
full VT/6h horizon.

**Leader election / orchestrator lock (`pg_orchestrator_lock`)** — a DB lease that
elects a single reaper/orchestrator across replicas; released on graceful shutdown so a
standby takes over promptly.

**Request-reply (`reply_key`)** — a *blocking* dispatch: the caller enqueues with a
`reply_key`, the consumer stores the result under it in `pg_task_result`, and the
caller polls for it (the PG analogue of Celery's `AsyncResult`). Mutually exclusive
with the callback form.

**Callback dispatch (`dispatch_with_callback`, `on_success` / `on_error`)** —
fire-and-forget: after the task runs, the consumer **self-chains** the success or error
continuation onto its queue via `_chain_continuation` (the PG analogue of Celery
`link` / `link_error`). No blocking caller.

**Fairness** — a header carried on a dispatch (`org_id`, workload type, priority) so a
PG-routed run mirrors Celery's fair scheduling.

---

## 3. Tables (`backend/pg_queue/models.py`)

| Table | Purpose |
|---|---|
| `pg_queue_message` | The queue itself — one row per message; claimed via `SKIP LOCKED` + VT |
| `pg_task_result` | Request-reply results / terminal task status, keyed by reply/task id; TTL'd (`expires_at`) + reaper-swept, `ON CONFLICT DO NOTHING` |
| `pg_barrier_state` | Fan-in barrier counter for batched executions (`remaining`, `last_progress_at`) |
| `pg_batch_dedup` | Batch-level dedup guard (prevents double-dispatch of a batch) |
| `pg_orchestration_claim` | Per-execution orchestration claim (`last_progress_at` for stuck detection) |
| `pg_orchestrator_lock` | Leader-election lease for the singleton reaper/orchestrator |
| `pg_periodic_schedule` | Periodic-schedule store (the Celery-Beat replacement) |

All PG-queue tables are **droppable side tables** that never touch
`WorkflowExecution` — the PG transport can be turned off and its tables
dropped without affecting the Celery path.

---

*Defaults here reflect the code constants at time of writing; the code
(`consumer.py` / `supervisor.py` / `reaper.py`) and the chart `values.yaml` are the
source of truth.*
