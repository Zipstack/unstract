# Pipeline list and aggregate

The ETL and Task pipeline pages page through `pipeline/` and read their status
counts and failing rows from `pipeline/aggregate/` (UN-4320, for Frontend v1
P4-T01 to P4-T03). The API deployment equivalents are in
[`api_v2/README.md`](../api_v2/README.md); the status and failing rules are the
same and are defined there.

This README and the `@extend_schema` annotations in `openapi_schema.py` are the
contract. Changes to anything below are contract changes. Neither endpoint is
in the published client spec.

- [Endpoints](#endpoints)
- [Filters](#filters)
- [Aggregate response](#aggregate-response)
- [Errors](#errors)

## Endpoints

Mounted under the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Returns |
|---|---|---|
| GET | `pipeline/` | A page of pipelines, most recent run first |
| GET | `pipeline/aggregate/` | Counts over every pipeline the list would return |

**Who may call it.** Whoever may call the list, seeing the same rows. Every
query is scoped to the caller's organisation.

## Filters

Both endpoints take the same filters, so the aggregate's `total` always equals
the list's `count`. A row must match every filter given. Blank values are
ignored. With none of the new filters, the list query and response are as
before.

| Parameter | Type | Meaning |
|---|---|---|
| `type` | `ETL`, `TASK`, `DEFAULT`, `APP` | Pipelines of this type. The ETL and Task pages always send it. |
| `workflow` | UUID | Pipelines of this workflow. |
| `search` | string | Name contains this text, case-insensitively. |
| `pipeline_name` | string | Exactly this name. |
| `status` | `success`, `error`, `never_run`, `inactive` | New. See the [status rule](../api_v2/README.md#status-rule); `inactive` means `active` is false. |
| `owner` | user id | New. Owned or co-owned by this user, as in `owner_emails`. |
| `last_run_after` | ISO 8601 datetime | New. `last_run_time` at or after this. |
| `last_run_before` | ISO 8601 datetime | New. `last_run_time` at or before this. |
| `failing` | boolean | New. `true` keeps only failing rows. See the [failing rule](../api_v2/README.md#failing-rule). |
| `ordering` | string | List only. |
| `page`, `page_size` | int | List only. |

`last_run_time` is the pipeline's own field, as the list shows it: it is set
when a run starts. A pipeline that has never run has none and is left out by
either bound.

## Aggregate response

### `GET pipeline/aggregate/`

```json
{
  "total": 5,
  "by_status": {"success": 1, "error": 2, "never_run": 1, "inactive": 1},
  "failing_count": 1,
  "not_scheduled": 2,
  "failing": [
    {
      "id": "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90",
      "owner_email": "sam@acme.com",
      "failures_in_a_row": 5,
      "failing_since": "2026-10-27T04:00:00Z",
      "last_failure": "2026-10-27T08:00:00Z",
      "last_success": null,
      "name": "hourly-invoices",
      "pipeline_type": "ETL",
      "next_run_time": "2026-10-28T09:30:00Z"
    }
  ]
}
```

- `not_scheduled` counts the active pipelines with no `cron_string`. It
  overlaps `by_status` rather than being one of its buckets.
- `next_run_time` comes from `cron_string`, as on the list; `null` when the
  pipeline has no schedule.
- The other fields are as for
  [API deployments](../api_v2/README.md#aggregate-response). `name` is the
  pipeline name.

The request takes a fixed number of queries, whatever the number of rows.

## Errors

Errors use the project's standard envelope (drf-standardized-errors), on both
endpoints:

| Status | When |
|---|---|
| 400 | A malformed new filter: an unknown `status`, `owner` not a positive integer, an unparsable datetime, or `failing` not a boolean. `attr` names the parameter. |
| 500 | `workflow` is not a UUID. The list has always answered this way, and the aggregate matches it. |
