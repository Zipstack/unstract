# Executions: stuck runs and abort

Finding executions that stopped making progress, and stopping running ones
(PB-T08, UN-4318). This README is the published contract, backed by the
`@extend_schema` annotations in `views/stuck_abort.py` and `views/execution.py`.
`stuck_since` is documented here only: the generated schema shows the plain list
row. Changes to anything below are contract changes.

- [Endpoints](#endpoints)
- [What counts as stuck](#what-counts-as-stuck)
- [Listing stuck executions](#listing-stuck-executions)
- [Counting stuck executions](#counting-stuck-executions)
- [Aborting executions](#aborting-executions)
- [Deploying](#deploying)
- [Limits](#limits)

## Endpoints

Paths are relative to the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Returns |
|---|---|---|
| GET | `execution/?stuck=true` | The existing execution list, narrowed to stuck runs |
| GET | `execution/stuck-count/` | Stuck runs per entity, and the threshold |
| POST | `execution/abort/` | One outcome per requested id |

Everything here is additive. The existing list, detail and log endpoints keep
their paths, parameters, response fields and permissions. Without `stuck`, or
with `stuck=false`, the list response is the same as before. Aborted runs are the
one new case the existing endpoints see; see
[How the work stops](#how-the-work-stops).

## What counts as stuck

An execution is stuck when its status is `PENDING` or `EXECUTING` and its last
activity is older than the threshold. Last activity is the later of the
execution row's `modified_at` and the newest `modified_at` of its file rows.

The threshold is `STUCK_EXECUTION_THRESHOLD_SECONDS` (env, default **9000**,
2.5 hours). It is returned as `threshold_seconds` by `stuck-count/`.

## Listing stuck executions

`GET execution/?stuck=true` takes the list's existing filters, ordering and
pagination. Each row has the usual fields plus:

| Field | Type | Meaning |
|---|---|---|
| `stuck_since` | ISO datetime | The time of last activity |

`stuck` accepts `true`/`1` and `false`/`0`, case-insensitive. Any other value
is ignored, as if `stuck` were absent. Visibility is the same as the list's.

## Counting stuck executions

`GET execution/stuck-count/` returns 200:

```json
{
  "threshold_seconds": 9000,
  "total": 3,
  "counts": {"API": 1, "ETL": 2, "TASK": 0, "WF": 0}
}
```

- `counts` uses the same keys as the list's `execution_entity` filter: `API`
  deployments, `ETL` and `TASK` pipelines, and `WF` for workflow runs without a
  pipeline.
- `total` counts every stuck run the caller can see. It can exceed the sum of
  `counts` when a run's pipeline was deleted or is of another type.
- Visibility is the same as the list's.

## Aborting executions

`POST execution/abort/` with:

```json
{"ids": ["3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90", "..."]}
```

`ids` holds 1 to 100 execution ids; duplicates are answered once. It returns
200, with results in request order:

```json
{
  "results": [
    {"id": "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90", "outcome": "aborted", "status": "STOPPED"},
    {"id": "57a4f9a2-2a4e-4a3c-8f0e-7c1d2b3a4f5e", "outcome": "already_finished", "status": "COMPLETED"},
    {"id": "9b1c2d3e-4f5a-4b6c-8d7e-0f1a2b3c4d5e", "outcome": "not_permitted", "status": null}
  ],
  "aborted": 1,
  "already_finished": 1,
  "not_permitted": 1,
  "failed": 0
}
```

| Outcome | When | `status` |
|---|---|---|
| `aborted` | The run was `PENDING` or `EXECUTING` and is now `STOPPED` | `STOPPED` |
| `already_finished` | The run was already `COMPLETED`, `ERROR` or `STOPPED`; nothing changed | its status |
| `not_permitted` | The caller may not abort it, or the id does not exist | `null` |
| `failed` | The abort hit an unexpected error for this id; retry it | `null` |

Unknown ids and ids the caller cannot abort get the same answer, so the
endpoint does not reveal which ids exist.

**Who may abort.** The owner of what started the run: an OWNER of its API
deployment or pipeline, or of its workflow when the run has no pipeline. Org
admins and service accounts (platform API keys with write access) may abort any
run in the organisation. Shared users who are not owners get `not_permitted`.

**What abort does.** In one transaction per id:

1. Sets the execution to `STOPPED` with the error `Execution aborted`, which
   also frees an API deployment's rate-limit slot and sends the existing
   "was stopped" inbox notice, unless the inbox item already shows a newer run.
2. Sets its `PENDING` and `EXECUTING` file rows to `STOPPED` with the same error,
   and stamps their execution time. Finished file rows, file history, destination
   writes and usage are kept.
3. Writes the run's file counts: finished files are successful, and every other
   file is failed.

Once that commits, it:

1. Sends the notifications of the run's pipeline (status `FAILURE`) or API
   deployment (status `STOPPED`), paused pipelines included. A failure here is
   logged and does not change the answer.
1. Sets the pipeline's last-run status to failure, unless the pipeline has a newer
   run.
2. Records an `execution.aborted` event in the platform audit log, with target
   `execution`, the workflow name, the summary `was <previous status>` and
   `previous_status`, `pipeline_id` and `entity` in its metadata. This is best
   effort: a lost event does not fail the abort and is not retried.

### How the work stops

- Queued batches of a stopped run are skipped when a worker picks them up, and
  still count down on the barrier. So does a batch that fails after the abort.
- A re-run ignores the active-file markers of a stopped run, so it keeps those
  files even if no worker has picked up the queued batch yet.
- A running batch checks the status before each file and stops once it is
  `STOPPED`: its remaining files are marked `STOPPED` and counted as failed.
- The file being processed when the abort lands finishes, and its own result
  replaces `STOPPED` on its row.
- The last batch fires the aggregating callback. It keeps the status `STOPPED`,
  saves the final file counts, commits usage for finished files, publishes the
  final log and cleans up the execution directory. It leaves the pipeline status
  and notifications to the abort.
- A caller waiting on a synchronous API deployment `POST` gets 422 for an aborted
  run, the same as polling with `GET`. Both apply the same result filters.
- Later status writes from workers cannot undo the abort, unless the run's
  `queue_message_id` is empty.

### Errors

400 uses the project's standard envelope (drf-standardized-errors). 401 and 403
come from the auth middleware as `{"message": "..."}`.

| Status | When |
|---|---|
| 400 | `ids` missing, empty, longer than 100, or holding a value that is not a UUID |
| 401 | Not authenticated |
| 403 | Authenticated but refused: a user outside the organisation, or a platform API key without write access |

A failure on one id answers `failed` for that id, and the other ids still run.
Each id is aborted in its own transaction, so the others are kept (unless
`ATOMIC_REQUESTS` is on, which can roll the whole request back). Retrying is safe:
ids already aborted answer `already_finished`.

## Deploying

Deploy the backend before the workers. Workers read the status from the
internal `GET /internal/v1/workflow-execution/<id>/status/` endpoint. An older
backend answers 404, and the worker then processes the file anyway (fail
open), as it did before this change.

Expose abort to users only once the workers are updated too. An older worker's
callback reports an aborted run with a finished file as completed.

## Limits

- The file being processed when the abort lands is not interrupted. A hung worker
  is covered in [`pg_queue/README.md`](../../../workers/queue_backend/pg_queue/README.md).
- **Re-running right after an abort can process a file twice.** The file still
  being processed no longer counts as active, so a manual or scheduled re-run can
  pick it up while the old worker finishes it: double LLM spend, and two writes to
  a database destination. Wait for that file to finish before re-running.
- **A dead worker's run never gets its callback.** The pipeline status,
  notifications and file counts are still set by the abort, but usage for its
  finished files is not committed and its execution directory, which can hold
  uploaded documents, is not cleaned up. It stays in storage until something else
  deletes it. The reaper's `ERROR` path has the same gap.
- A run whose `queue_message_id` is empty (from before the PG queue, or whose
  handle write failed) is not protected from a late worker status write.
- The file being processed when the abort lands is billed once it finishes, but an
  API caller can't get its result: the first read after the abort returns the
  results so far and discards them, and later reads answer 406. Its processing cost
  was already spent, the same as for a caller who never collects a result.
- A running batch stops between files only for `STOPPED`. A run that becomes
  `ERROR` or `COMPLETED` mid-batch keeps processing its files, as before.
