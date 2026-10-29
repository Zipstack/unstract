# API deployment list and aggregate

The API Deployments page pages through `api/deployment/` and reads its status
counts and failing rows from `api/deployment/aggregate/` (UN-4320, for Frontend
v1 P4-T01 to P4-T03). The pipeline equivalents are in
[`pipeline_v2/README.md`](../pipeline_v2/README.md).

This README and the `@extend_schema` annotations in `openapi_schema.py` are the
contract. Changes to anything below are contract changes. The list is also in
the published client spec (`specs/docstudio-oss.json`); the aggregate is not.

- [Endpoints](#endpoints)
- [Filters](#filters)
- [Status rule](#status-rule)
- [Failing rule](#failing-rule)
- [Aggregate response](#aggregate-response)
- [Errors](#errors)

## Endpoints

Mounted under the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Returns |
|---|---|---|
| GET | `api/deployment/` | A page of deployments, most recent run first |
| GET | `api/deployment/aggregate/` | Counts over every deployment the list would return |

**Who may call it.** Whoever may call the list, seeing the same rows: a member
sees the deployments they own, are shared on, or that are shared with the
organisation or one of their groups; organisation admins, service accounts and
platform API keys see all of the organisation's. Every query is scoped to the
caller's organisation.

## Filters

Both endpoints take the same filters, so the aggregate's `total` always equals
the list's `count`. A row must match every filter given. Blank values are
ignored. With none of the new filters, the list query and response are as
before.

| Parameter | Type | Meaning |
|---|---|---|
| `search` | string | Display name contains this text, case-insensitively. |
| `workflow` | UUID | Deployments of this workflow. |
| `api_name` | string | Exactly this `api_name`. |
| `status` | `success`, `error`, `never_run`, `inactive` | New. See [Status rule](#status-rule). |
| `owner` | user id | New. Owned or co-owned by this user, as in `owner_emails`. |
| `last_run_after` | ISO 8601 datetime | New. `last_run_time` at or after this. |
| `last_run_before` | ISO 8601 datetime | New. `last_run_time` at or before this. |
| `failing` | boolean | New. `true` keeps only failing rows. See [Failing rule](#failing-rule). |
| `page`, `page_size` | int | List only. |

`last_run_time` is the row's newest run of any status, as the list shows it. A
deployment that has never run has none and is left out by either bound.

## Status rule

A deployment's status comes from its latest finished run (COMPLETED, STOPPED or
ERROR). PENDING and EXECUTING runs are skipped, so a run that was never picked
up does not count.

| Status | When |
|---|---|
| `inactive` | `is_active` is false. Wins over everything below. |
| `success` | The latest finished run is COMPLETED, even if some of its files failed. |
| `error` | The latest finished run is ERROR or STOPPED. |
| `never_run` | No finished run. |

The four counts in `by_status` always sum to `total`.

## Failing rule

A deployment is failing when it is active and each of its last five finished
runs ended in ERROR. A STOPPED run breaks the streak. This is the rule the
dashboard's "needs attention" feed uses
(`workflow_manager/workflow_v2/failing_streaks.py`). `failing=true` and
`failing_count` both use it, so they agree.

## Aggregate response

### `GET api/deployment/aggregate/`

```json
{
  "total": 5,
  "by_status": {"success": 1, "error": 2, "never_run": 1, "inactive": 1},
  "failing_count": 1,
  "failing": [
    {
      "id": "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90",
      "owner_email": "sam@acme.com",
      "failures_in_a_row": 5,
      "failing_since": "2026-10-27T04:00:00Z",
      "last_failure": "2026-10-27T08:00:00Z",
      "last_success": "2026-10-27T03:00:00Z",
      "name": "Receipts"
    }
  ]
}
```

- `failing` holds at most 100 rows, newest `last_failure` first.
  `failing_count` counts all of them.
- `failures_in_a_row` counts the ERROR runs since the last finished run that
  was not one, so it can be more than five. `failing_since` is the first of
  them.
- `last_success` is the latest COMPLETED run, or `null`.
- `owner_email` is the earliest owner, or `null` when no owner is a person.
- `name` is the display name.

The request takes a fixed number of queries, whatever the number of rows.

## Errors

Errors use the project's standard envelope (drf-standardized-errors), on both
endpoints:

| Status | When |
|---|---|
| 400 | A malformed filter: `workflow` not a UUID, an unknown `status`, `owner` not a positive integer, an unparsable datetime, or `failing` not a boolean. `attr` names the parameter. |
| 401, 403 | As for the list. |
