# Connection check

Stores the result of the latest connection test of each saved adapter and
connector. It backs the connection status, the "failing" banner and the Status
filter on the adapter and connector lists (Frontend v1 P2-T12).

This README and the `@extend_schema` annotations in `schema.py` are the
published contract (PB-T10, UN-4312). Changes to anything below are contract
changes.

- [Test and record](#test-and-record)
- [Status fields on list and detail](#status-fields-on-list-and-detail)
- [List filters](#list-filters)
- [Paged envelope](#paged-envelope)
- [What is not recorded](#what-is-not-recorded)

## Test and record

Mounted under the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Tests |
|---|---|---|
| POST | `adapter/{id}/test/` | The saved adapter, with its stored settings |
| POST | `connector/{id}/test/` | The saved connector, with its stored credentials |

No request body. The test is the same one `test_adapters/` and
`test_connectors/` run; the result is stored and returned.

```json
{
  "status": "failed",
  "tested_at": "2026-10-28T09:30:12.481000Z",
  "failure_reason": "Error testing 'my-openai'. Incorrect API key provided."
}
```

- `status` is `connected` or `failed`. A failed test is still a **200**.
- `tested_at` is when the test started.
- `failure_reason` is `null` when connected. When failed it is the error text
  `test_adapters/` or `test_connectors/` would show for the same settings,
  trimmed to 500 characters. A test that reports "not connected" without an
  error stores `The connection test did not succeed.`; an unexpected error
  stores a generic reason and is logged.
- A new test replaces the stored result.
- OAuth connectors have their tokens refreshed first when they have expired.

**Who may call it.** Anyone who may edit the profile: its owners, organisation
admins and service accounts. Others get **403**. Frictionless (Unstract
provided) adapters cannot be edited, so they get **403** too. A profile the
caller cannot see, including one in another organisation, is a **404**.

| Status | When |
|---|---|
| 200 | Tested and stored, whether connected or failed |
| 403 | The caller may not edit the profile |
| 404 | No such profile visible to the caller |

`test_adapters/` and `test_connectors/` are unchanged and store nothing.

## Status fields on list and detail

The list, detail, create and update responses of `adapter/` and `connector/`
end with four keys, after every existing key:

| Key | Type | Meaning |
|---|---|---|
| `last_test_status` | `connected` \| `failed` \| `never_tested` | Outcome of the latest stored test |
| `last_tested_at` | datetime or `null` | When that test started |
| `last_failure_reason` | string or `null` | Set only when `failed` |
| `tested_before_last_change` | bool | The profile's `modified_at` is later than `last_tested_at`; `false` when never tested |

`tested_before_last_change` follows `modified_at`, so anything that saves the
profile sets it: an edit, but also turning org-wide sharing on or off, or an
OAuth token refresh.

Other responses that embed a connector or adapter, such as workflow endpoints,
do not carry these keys.

## List filters

Optional, on `GET adapter/` and `GET connector/`, combined with the existing
filters:

| Parameter | Values | Meaning |
|---|---|---|
| `failing` | `true` (any case) | Only profiles whose latest test failed |
| `last_test_status` | `connected`, `failed`, `never_tested` | Only profiles with this status |

Any other value of either parameter is ignored, and the list is returned as if
it were absent.

## Paged envelope

A list fetched with `page` or `page_size` adds `failing_count`, after
`results`: the number of failing profiles across every page. It applies the
request's other filters (search, adapter type, connector mode, ...) but not
`failing` or `last_test_status`, so it stays the same while those change.

```json
{"count": 12, "next": "…?page=2", "previous": null, "results": [], "failing_count": 2}
```

A list fetched without `page` and `page_size` is still a bare array, without
`failing_count`.

## What is not recorded

Only tests run through the two endpoints above are stored. Failures during
real runs (workflows, API deployments, Prompt Studio) are not recorded, and
nothing is backfilled, so every profile starts as `never_tested`.
