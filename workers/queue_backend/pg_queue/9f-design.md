# 9f — Multi-queue PG consumer + symmetric `pg` run-set (consumer ergonomics)

**Status:** scoped, queued behind PR 3 (Flipt canary). Sibling sub-task under the
9 transport-engine story. **Gated-off-safe** — no runtime behaviour change until
PG consumers are actually run; PR 3's flag stays the only on/off switch.

---

## 1. Problem

The PG consumer today is **single-queue + single-registry**, which makes running
the PG substrate asymmetric with — and much harder than — the Celery fleet.

- **Single queue per process.** `PgQueueConsumer` takes a scalar
  `queue_name: str` and dequeues `read(self.queue_name, …)`
  (`consumer.py:73,120`). N queues ⇒ N processes.
- **Single task-registry per process.** `pg_queue_consumer/__main__` sets
  `WORKER_TYPE` from `WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE` and `worker.py`
  imports exactly **one** worker's tasks module. A fan-out consumer literally
  does not have `process_batch_callback_api` registered, and vice-versa.

A **Celery** worker has neither limit: `--queues=file_processing,api_file_processing`
is multi-queue, and its registry is whatever that worker loads. That asymmetry is
the whole pain:

| | Celery (today) | PG consumer (today) |
|---|---|---|
| Coupled pipeline coverage | **2** processes (fan-out worker + callback worker, each ETL+API) | **4** processes (one per queue) |
| Config | `--queues` baked into the worker map | per-process `WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE` + `-q` + distinct `-p` |
| One-command launch | `run-worker.sh all` | none — the `pg` set launches the *default* (notification) consumer, useless for the pipeline |

So an operator must hand-roll 4 launches with per-process env, and the `pg`
run-set (`run_pg_queue_set`) is wired to the default consumer, not the pipeline.

**Decision already taken (do NOT split the build):** the celery worker and the
PG consumer run the *same task code* — the only difference is the runtime loop
(`celery -A worker` vs `python -m pg_queue_consumer`), a **command** difference,
not a code one. Two images would duplicate ~all task code, add a second
CI/version axis, and violate the repo rule *"never duplicate logic in workers."*
The split belongs at the **process / Deployment** level (already true), not the
image. 9f keeps the **single build** and makes the **single script** symmetric.

---

## 2. Goal

Make the PG substrate as easy to run as the Celery one — **single build, single
script, env set once** — with the option (not the obligation) to split by queue
for scale.

```bash
./run-worker.sh -d all   # celery substrate            (already one command)
./run-worker.sh -d pg    # pg substrate: consumer(s)+reaper, queues baked in
```

Cloud: **one** `pg-consumer` Deployment (env = queue list, set once in its
manifest) + a 1-replica `pg-reaper`; scale by replicas, split by queue only if
you want fan-out/callback to scale independently.

---

## 3. Design

### 3a. Multi-queue consumer (mirror Celery `--queues=a,b`)

- `PgQueueConsumer.__init__`: `queue_name: str` → `queue_names: list[str]`.
- `WORKER_PG_QUEUE_CONSUMER_QUEUE` becomes **comma-separated** (parsed in the
  `_env("QUEUE", …)` path in `consumer.py:main`). A single value still works
  (list of one) → backward compatible; the leaf-webhook consumer is unaffected.
- **Dequeue across queues by round-robin**, NOT one `queue_name = ANY(...)`
  blanket scan: poll each queue in turn with the existing single-queue
  `read(q, …)`. Round-robin (a) preserves the `(queue_name, priority DESC,
  msg_id)` dequeue index's top-N efficiency per queue, and (b) gives simple
  cross-queue fairness (no queue starves another). Per-queue priority + FIFO
  ordering is unchanged. `poll_once` returns the total claimed across the
  rotation; the heartbeat timestamp updates at the top of the rotation (liveness
  unchanged).
- The liveness/`_last_poll_monotonic` contract is unchanged — one rotation =
  one poll cycle.

### 3b. Broad task registry (load what the queues need)

The consumer must have every task it might dequeue registered in
`current_app.tasks`. Two viable shapes — pick one in build:

1. **Configurable worker-type list** (preferred, minimal new code):
   `WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE` becomes comma-separated; the
   `__main__` bootstrap loops the existing tasks-module import over each type
   (e.g. `file_processing,callback`). Reuses `worker.py`'s import machinery.
2. **Dedicated `pg_pipeline` tasks module** that imports the coupled-pipeline
   tasks (`process_file_batch(_api)`, `process_batch_callback(_api)`, barrier
   tasks). One bootstrap, no per-type loop.

Either way a single consumer process can run both fan-out and callback. Cost is
a few extra module imports in one process (all already in the single build) —
negligible.

### 3c. Wire the `pg` run-set to the pipeline

`run_pg_queue_set` already launches consumer + reaper with all-or-nothing
teardown. Change: launch the consumer with the **pipeline queues baked into the
set definition** (one source of truth, like the celery worker map):

```
pg set → pg-queue-consumer
           WORKER_PG_QUEUE_CONSUMER_QUEUE=file_processing,api_file_processing,\
                                          file_processing_callback,api_file_processing_callback
           WORKER_PG_QUEUE_CONSUMER_WORKER_TYPE=file_processing,callback
       + reaper
```

So `./run-worker.sh -d pg` brings up the whole PG substrate in one command,
env-free at the call site. A scale-split is still available by launching
`pg-queue-consumer` directly with a narrower `-q` list.

---

## 4. Cloud topology (symmetric to celery)

| Deployment | command | env (set once, per-Deployment) |
|---|---|---|
| `worker-file-processing`, `worker-callback`, `worker-general`, … | `celery -A worker` | `--queues=…` |
| **`pg-consumer`** | `python -m pg_queue_consumer` | `WORKER_PG_QUEUE_CONSUMER_QUEUE=<pipeline queue list>`, `…_WORKER_TYPE=file_processing,callback` |
| **`pg-reaper`** | `python -m pg_queue_reaper` | lease/health tunables; `replicas: 1` |

Same image everywhere; the `command` + env decide what a pod is — the existing
"same image, different command" pattern (cf. the log-history-scheduler). Roll
out the `pg-consumer` Deployment **before** flipping `pg_queue_execution_enabled`
(the deploy-ordering safety). Split into `pg-consumer-fanout` /
`pg-consumer-callback` only if you want independent scaling.

---

## 5. Out of scope

- The orchestrator-on-PG move (`async_execute_bin` itself) — that's 2d.
- Any change to the Flipt decision / PR 3.
- A cross-queue *weighted* fairness policy — round-robin is enough for 9f; a
  weighting knob (e.g. drain fan-out N× per callback poll) can come later if a
  real imbalance shows up.

## 6. Test plan

- **Unit:** comma-parse of the queue env (incl. single-value back-compat);
  round-robin polls each queue and aggregates the claimed count; an empty queue
  in the list is skipped without starving the others; per-queue priority+FIFO
  preserved.
- **Registry:** a consumer booted with `WORKER_TYPE` list (or the `pg_pipeline`
  module) resolves *both* `process_file_batch_api` and `process_batch_callback_api`.
- **run-worker.sh:** `pg` set launches a single consumer covering all four
  pipeline queues + the reaper; `-k`/`-s` still treat the set coherently.
- **e2e:** one `./run-worker.sh -d pg` consumer drains **both** an ETL and an
  API pg_queue execution end-to-end (the 9e dev-test recipe, but one consumer
  instead of four).

## 7. Migration / compatibility

- Single-queue env (`WORKER_PG_QUEUE_CONSUMER_QUEUE=notifications`) still valid →
  the existing leaf-webhook consumer and any current launches keep working.
- No schema change, no API change. Gated-off-safe.
