# Connection check

Stores the result of the latest connection test of each saved adapter and
connector. It backs the connection status, the "failing" banner and the Status
filter on the adapter and connector lists (Frontend v1 P2-T12).

This README, the `@extend_schema` annotations in `schema.py` and the
`failing_count` schema in `pagination.py` are the published contract (PB-T10,
UN-4312). The four status keys on list and detail are defined in this README
only, not in the generated schema. Changes to anything below are contract
changes.

- [Test and record](#test-and-record)
- [Status fields on list and detail](#status-fields-on-list-and-detail)
- [List filters](#list-filters)
- [Paged envelope](#paged-envelope)
- [What is not recorded](#what-is-not-recorded)
- [Deploying and rolling back](#deploying-and-rolling-back)

## Test and record

Mounted under the organisation path: `/api/v1/unstract/{org_id}/`.

| Method | Path | Tests |
|---|---|---|
| POST | `adapter/{id}/test/` | The saved adapter, with its stored settings |
| POST | `connector/{id}/test/` | The saved connector, with its stored credentials |

No request body. The test is the same one `test_adapters/` and
`test_connectors/` run; the result is returned, and stored unless a test that
started later is already stored.

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
- A new test replaces the stored result, unless a test that started later is
  already stored.
- OAuth connectors are tested with their stored tokens, the same ones a real run
  reads. Nothing is refreshed first.

**Who may call it.** Anyone who may edit the profile: its owners, organisation
admins and service accounts. Others get **403**. Frictionless (Unstract
provided) adapters cannot be edited, so they get **403** too. A profile the
caller cannot see, including one in another organisation, is a **404**.

| Status | When |
|---|---|
| 200 | Tested, whether connected or failed |
| 403 | The caller may not edit the profile |
| 404 | No such profile visible to the caller, or it was deleted during the test |

`test_adapters/` and `test_connectors/` are unchanged and store nothing.

## Status fields on list and detail

The list, detail, create and update responses of `adapter/` and `connector/`
end with four keys, after every existing key:

| Key | Type | Meaning |
|---|---|---|
| `last_test_status` | `connected` \| `failed` \| `never_tested` | Outcome of the latest stored test |
| `last_tested_at` | datetime or `null` | When that test started |
| `last_failure_reason` | string or `null` | Set only when `failed`. On adapters, `null` for callers who can't edit the adapter |
| `tested_before_last_change` | bool | The profile's `modified_at` is later than `last_tested_at`; `false` when never tested |

`tested_before_last_change` follows `modified_at`, so anything that saves the
profile sets it: an edit, but also turning org-wide sharing on or off.

Other responses that embed a connector or adapter, such as workflow endpoints,
do not carry these keys.

## List filters

Optional, on `GET adapter/` and `GET connector/`, combined with the existing
filters:

| Parameter | Values | Meaning |
|---|---|---|
| `failing` | `true` (any case) | Only profiles whose latest test failed |
| `last_test_status` | `connected`, `failed`, `never_tested` (any case) | Only profiles with this status |

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

## Deploying and rolling back

- The migration must apply before this code serves. Adapter and connector list,
  create and per-profile endpoints read the new tables, so they return **500**
  until it does. Create saves the row before it fails, so a retry hits the
  duplicate-name error.
- Older code doesn't know these tables, so it can't delete a tested profile: the
  foreign key fails and the delete returns **500**. Profiles with no stored
  result delete normally.
- To roll back to an image without this app, roll the image back first. This
  code needs the tables until the last of its pods is gone. Then run
  `.venv/bin/python manage.py migrate connection_check zero` as a one-off from
  this image. It drops every stored result.
- If that image is already gone, run this instead:

  ```sql
  SET search_path TO unstract;  -- or whatever DB_SCHEMA is set to
  DROP TABLE adapter_test_result, connector_test_result;
  DELETE FROM django_migrations WHERE app = 'connection_check';
  ```
