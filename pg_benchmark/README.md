# pg_benchmark — PG-queue vs Celery execution benchmark harness

A self-contained harness to compare the **PG-queue transport** against the
**Celery/RabbitMQ transport** for Unstract workflow executions — functional
parity, performance, and (later) load/soak. This is the **gate** that must show
`PG ≥ Celery` before any Celery decommission (epic UN-3445).

It is dev/ops tooling, not product code: a new top-level directory, no imports
into backend/workers, non-regressive by construction.

## Latency model (why it measures what it measures)

The harness deliberately leans on **persistent, server-measured** signals:

| Signal | Source | Persistent? |
|---|---|---|
| `execution_time` (server) | `workflow_execution.execution_time` | ✅ truest cross-transport number — excludes harness HTTP/poll overhead |
| per-file `execution_time` | `workflow_file_execution.execution_time` | ✅ exposes **parallelism** (the key fan-out signal) |
| transport class | `queue_message_id` / `task_id` columns | ✅ survive on the row after the queue message is deleted |
| wall-clock E2E | harness client clock (trigger → terminal) | ✅ (only when the harness triggers the run) |
| enqueue→pickup | `pg_queue_message.enqueued_at` / `vt` | ❌ **ephemeral** — row deleted on ack; only observable by *live sampling* during a run |

**Parallelism** `= sum(file_times) / execution_time`: `≈ N` means all N files
overlapped (ideal fan-out), `≈ 1` means they ran serially. This directly
measures the serial-fileproc concern on the PG path.

> Transport micro-latency (enqueue→pickup, the SKIP-LOCKED-poll-vs-push KPI) is
> **not** readable post-hoc — those queue rows are deleted on ack. It needs a
> live sampler that watches `pg_queue_message` while a run is in flight; that is
> a later slice.

## Status — slices

- **S1 (this slice): measurement spine.** `report` + `queue-depth` read the DB
  directly and print a per-transport latency comparison. Read-only.
- **S2: load generation.** `run` — trigger N executions at concurrency C against
  a running stack, flip the transport, collect wall-clock + server latency.
- **S3: live transport sampler.** Capture enqueue→pickup + queue depth during a
  run (PG-only).
- **S4: functional parity matrix.** Flag OFF vs ON across workflow shapes.

## Usage

```bash
cd pg_benchmark
pip install -r requirements.txt   # or use the backend .venv (has psycopg2)

# Compare the last 200 finished executions, all transports side by side:
python -m pg_benchmark report --last 200

# Just the PG path:
python -m pg_benchmark report --last 200 --transport pg

# Current live queue depth per queue:
python -m pg_benchmark queue-depth
```

DB connection defaults mirror the local docker-compose stack
(`localhost:5432/unstract_db`, schema `unstract`). Override via `DB_HOST`,
`DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` env vars or the `--db-*` flags.

### Triggering a real deployment

`run` POSTs to an API deployment. The execute response nests the `execution_id`
inside `message.status_api` (a `?execution_id=` query param) — the harness parses
that automatically. Subscription headers + form fields the deployment expects are
passed through:

```bash
python -m pg_benchmark run --n 1 --concurrency 1 \
  --path /deployment/api/<org>/<api>/ --api-key <key> \
  --file /path/to/doc.pdf \
  --header X-subscription-id:sub-1 --form tags=bench --form timeout=300
```

## Zero-cost load testing (mock adapters)

Real LLM/extraction calls cost money **and** are a poor transport signal — a 20s
LLM call swamps the millisecond queue differences. For a true PG-vs-Celery
**transport** benchmark, mock the adapters so cost = $0 and execution time ≈
queue + dispatch + fan-out:

1. **LLM + embedding** → the bundled mock server (instant, OpenAI-compatible):

   ```bash
   python -m pg_benchmark.mock_server --port 8901   # POST /v1/chat/completions + /v1/embeddings
   ```

   Then set an **OpenAI-compatible** LLM and embedding adapter's `api_base` to
   `http://<host>:8901/v1`. `--latency-ms` can simulate adapter latency; `--content`
   sets the canned answer.

2. **Extraction + vector DB** → Unstract's built-in **`noOpX2text`** and
   **`noOpVectorDb`** adapters (instant, free, active by default).

Wire a "benchmark" workflow to those four adapters, expose it as an API
deployment, then fire load through the **same** transport-comparison protocol:
run a batch with the flag/gate **off** (Celery) and another **on** (PG) against
the same deployment — the runner buckets each execution by its observed transport.

## Tests

```bash
cd pg_benchmark
pytest            # pure stats + classification + parallelism (no DB needed)
```
