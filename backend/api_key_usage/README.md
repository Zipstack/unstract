# API key usage, expiry and rotation

How often each API key is used, when it expires, and how its secret is rotated.
It backs the key pages of Frontend v1 (Settings → API keys, deployment keys) and
covers platform API keys and global API deployment keys. Other key types (the
cloud's Human Review keys) plug in through the [registry](#adding-a-key-type).

This README and the `@extend_schema` annotations on the views are the published
contract (UN-4360, PB-T05). Changes to anything below are contract changes. All
changes are additive: existing fields and endpoints behave as before.

- [Endpoints](#endpoints)
- [Usage fields on the key lists](#usage-fields-on-the-key-lists)
- [History](#history)
- [Callers](#callers)
- [Summary](#summary)
- [Expiry](#expiry)
- [Rotation with a grace period](#rotation-with-a-grace-period)
- [How usage is recorded](#how-usage-is-recorded)
- [Adding a key type](#adding-a-key-type)

## Endpoints

Mounted under the organisation path `/api/v1/unstract/{org_id}/`.

| Method | Path | Returns | New |
|---|---|---|---|
| GET | `platform-api/keys/` | Platform keys, now with usage fields | fields |
| GET | `platform-api/keys/{id}/` | One platform key, now with usage fields | fields |
| GET | `platform-api/keys/{id}/history/` | Daily calls, last 30 days | yes |
| POST | `platform-api/keys/{id}/rotate/` | Accepts `grace` | body |
| GET | `global-api-deployment/keys/` | Global deployment keys, now with usage fields | fields |
| GET | `global-api-deployment/keys/{id}/` | One global key, now with usage fields | fields |
| GET | `global-api-deployment/keys/{id}/history/` | Daily calls, last 30 days | yes |
| GET | `global-api-deployment/keys/{id}/callers/` | Deployments the key called | yes |
| POST | `global-api-deployment/keys/{id}/rotate/` | Accepts `grace` | body |
| GET | `platform/key-usage/summary/` | Counts of keys needing attention | yes |

**Who may call them.** The same callers as the key's other endpoints:

- Platform key history: organisation admins on a session.
- Global key history and callers: admins, and members whose organisation lets
  members manage API keys, for keys they may already view (keys they created as
  a member). Anyone else gets 403.
- Summary: organisation admins on a session. Members, service accounts and
  platform API keys get 403.

Every read first moves pending usage from Redis to the database, so the numbers
include calls made seconds ago.

## Usage fields on the key lists

The list, detail, create and rotate responses of both key types carry:

| Field | Type | Meaning |
|---|---|---|
| `last_used_at` | datetime or null | Last successful authentication. Null if never used since tracking began. |
| `calls_30d` | int | Calls in the last 30 UTC days, today included. |
| `usage_status` | enum | See below. |
| `expires_at` | datetime or null | When the key stops working. Null never expires. List only; set it on create or PATCH. |
| `previous_key_expires_at` | datetime or null | Until when the secret before the last rotation still works. |

`usage_status` is the first of these that applies:

| Value | When |
|---|---|
| `expired` | `expires_at` has passed. The key gets 401. |
| `expiring` | `expires_at` is within 7 days. |
| `never_used` | No recorded use. |
| `idle` | Last used more than 90 days ago. |
| `active` | Anything else. |

**Tracking starts when this ships.** Every key created earlier shows
`never_used` until its next call. There is no backfill.

## History

`GET platform-api/keys/{id}/history/`, `GET global-api-deployment/keys/{id}/history/`

```json
{
  "key_id": "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90",
  "days": [
    {"day": "2026-09-30", "calls": 0},
    {"day": "2026-10-01", "calls": 14},
    "... 30 entries, oldest first, today last ..."
  ],
  "total_calls": 412,
  "last_used_at": "2026-10-29T09:30:12.481000Z",
  "usage_status": "active"
}
```

Always 30 entries. Days are UTC. Days without calls are present with `0`.

## Callers

`GET global-api-deployment/keys/{id}/callers/`

The API deployments the key authenticated in the last 30 UTC days, most calls
first.

```json
[
  {
    "api_deployment_id": "9b2e…",
    "display_name": "Invoice extractor",
    "api_name": "invoices",
    "calls": 380,
    "last_call_at": "2026-10-29T09:30:12.481000Z"
  }
]
```

A deployment deleted since keeps its counts, with `display_name` and `api_name`
null. Platform keys have no callers endpoint: they authenticate platform APIs,
not deployments.

## Summary

`GET platform/key-usage/summary/`

```json
{
  "never_used": 3,
  "expiring_7d": 1,
  "idle_90d": 2,
  "by_type": {
    "platform_api_key": {"never_used": 1, "expiring_7d": 1, "idle_90d": 1},
    "global_api_deployment_key": {"never_used": 2, "expiring_7d": 0, "idle_90d": 1}
  }
}
```

- Counts **active** keys only (`is_active: true`).
- A key counts once, under its `usage_status`, so the summary matches the lists.
  An unused key that expires in 3 days is counted as `expiring_7d`, not
  `never_used`. Expired keys are not counted.
- `by_type` has one entry per registered key type; a cloud deployment adds its
  own.
- There is no `plain_text` count: every key type here is stored as a plain
  UUID, so it would always equal the number of keys.

## Expiry

`expires_at` is optional on create and on PATCH of both key types. It must be in
the future; `null` removes the expiry. Setting, changing or clearing it records
`key.expiry_set` in the platform audit log with the before and after values.

An expired key gets **401** and its call is not counted. The body keeps each
auth path's existing format:

| Key type | Body |
|---|---|
| Platform API key | `{"message": "API key expired"}` |
| Global deployment key | `{"type": "client_error", "errors": [{"code": "error", "detail": "API key expired", "attr": null}]}`, the standard error body (`ExpiredKey`, a subclass of `UnauthorizedKey`) |

Unknown and inactive keys get the same generic 401 as before.

## Rotation with a grace period

`POST …/keys/{id}/rotate/` on both key types now accepts an optional body:

```json
{"grace": "24h"}
```

| `grace` | Old secret works for |
|---|---|
| `none` (default) | Not at all: cut off immediately, as before. |
| `1h` | 1 hour |
| `24h` | 24 hours |
| `7d` | 7 days |

Any other value is a 400. The response is the key's detail with the new secret
and `previous_key_expires_at`. Only the latest old secret is kept: rotating again
replaces it, and rotating with `none` cuts every old secret off. Deactivating the
key rejects both secrets. The `key.rotated` audit event's summary says until when
the old secret works; it never contains a secret.

Platform key rotate also checks the `manage_api_keys` capability
(`RequiresCapability`, PB-T04). Global key rotate already did through
`CanManageApiKeys`.

## How usage is recorded

- Each successful authentication of a platform key (`CustomAuthMiddleware`) or
  global key (`DeploymentHelper.validate_api`) calls `record_key_use`. It adds
  to Redis hashes in one round trip, never writes the database, and never fails
  the request.
- A flush moves the counts to `api_key_usage_daily`, `api_key_caller_daily` and
  `api_key_last_used`. The first use in each `API_KEY_USAGE_FLUSH_INTERVAL_SECONDS`
  (default 300) starts one in a background thread, and every read starts one.
  No scheduler is needed, so it works the same on Celery and PG-queue
  deployments.
- Each use is one atomic Redis script, and a flush moves all pending counts
  aside in one atomic step. The counts and the batch's token commit in one
  transaction before the batch leaves Redis, so a flush killed midway loses
  nothing and a retried batch is never counted twice.
- Daily rows older than 30 days are deleted on flush. `last_used_at` is kept for
  as long as the key exists, so `idle` can be computed.

## Adding a key type

```python
from api_key_usage.recorder import record_key_use
from api_key_usage.registry import register_key_type

# In your AppConfig.ready():
register_key_type("review_api_key", lambda org: ReviewApiKey.objects.filter(organization=org))

# Where the key authenticates:
record_key_use(key_type="review_api_key", key_id=key.id, organization_id=org.pk)
```

The queryset's rows need `id`, `is_active` and `expires_at`. Use
`api_key_usage.reads.usage_by_key` and `daily_history` for the key type's own
list and history endpoints, and `KeyUsageFieldsMixin` for its serializer.
