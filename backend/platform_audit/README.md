# Platform audit log

An organisation-scoped record of admin-visible platform changes: member roles,
invitations, groups, keys, default profiles and platform settings. It backs the
**Settings → Audit log** tab (Frontend v1 P3-T09) and is the recording API for
other tasks that emit events (PB-T04 capabilities, PB-T05 key expiry, PB-T08
execution aborts).

This README and the `@extend_schema` annotations in `views.py` are the published
contract (UN-4398). Changes to anything below are contract changes.

- [Read API](#read-api)
- [Recording events](#recording-events)
- [Action vocabulary](#action-vocabulary)
- [Retention](#retention)
- [What is not recorded](#what-is-not-recorded)

## Read API

Mounted under the organisation path:
`/api/v1/unstract/{org_id}/platform/audit/`.

| Method | Path | Returns |
|---|---|---|
| GET | `platform/audit/` | A page of events, newest first |
| GET | `platform/audit/export/` | The same filter as a CSV download |
| GET | `platform/audit/actions/` | The action vocabulary |
| GET | `platform/audit/actors/` | Distinct actors in the retention window |

**Who may call it.** Organisation admins on a session. Members, service
accounts and platform API keys (any tier) get **403**. Every query is scoped to
the caller's organisation and to the retention window.

### Filters (list and export)

| Parameter | Type | Meaning |
|---|---|---|
| `action` | string, repeatable | Match any of these keys. An unregistered key is a 400. |
| `actor` | e-mail | Actor e-mail, case-insensitive exact match. |
| `from` | ISO date or datetime | Inclusive start. A date means 00:00 UTC that day. |
| `to` | ISO date or datetime | Inclusive end. A date covers the whole day (UTC). |
| `search` | string ≤ 200 | Case-insensitive substring of actor e-mail, actor name, key name, target name or summary. |
| `page`, `page_size` | int | List only. Default 50, max 1000. |

With no `from`, the window starts at the retention cutoff; a `from` earlier
than the cutoff does not reveal expired events. `from` must not be after `to`.
Results are always newest first; an `ordering` parameter is ignored.

### `GET platform/audit/`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "retention_days": 365,
  "results": [
    {
      "id": "3f0d6c1e-5a0b-4a39-9a7e-0d6f3c2b1a90",
      "occurred_at": "2026-10-15T09:30:12.481000Z",
      "actor": {
        "id": 42,
        "email": "priya@acme.com",
        "name": "Priya Raman",
        "type": "user",
        "key_id": "",
        "key_name": ""
      },
      "action": "member.role_changed",
      "action_label": "Role changed",
      "target": {"type": "member", "id": "57", "name": "sam@acme.com"},
      "summary": "user → admin",
      "changes": {"before": {"role": "user"}, "after": {"role": "admin"}},
      "request_id": "6c1f0f2e-8d0e-4b8e-9a51-1b2f3e4d5c6a"
    }
  ]
}
```

- `actor.type` is `user`, `api_key` or `system`. For `api_key`, `key_id` and
  `key_name` name the platform API key that made the call, `email` is its
  service account and `name` is the key name.
- `actor.id` is `null` once the user is deleted; `email` and `name` are copied
  onto the event and survive.
- `changes` holds only what changed. Either side may be absent: a create has
  only `after`, a delete only `before`. When the previous value could not be
  read, `before` is absent and the summary ends with
  `(previous value unavailable)`; `after`, when present, is a snapshot of the
  current values, not a diff. A `member.removed` whose member could not be
  read has an empty `target.id`, empty `changes` (`{}`), and the summary
  `membership not confirmed (previous value unavailable)`.
- `role` values are whatever the deployment's auth plugin uses (`user`/`admin`
  in OSS, `unstract_user`/`unstract_admin` in cloud); do not hard-code them.
- `action_label` falls back to the raw key for an action that is no longer
  registered.

### `GET platform/audit/export/`

`text/csv; charset=utf-8`, `Content-Disposition: attachment;
filename="platform_audit_<YYYYmmdd_HHMMSS>.csv"`. Columns:

```
occurred_at, actor_type, actor_email, actor_name, actor_key_name, action,
action_label, target_type, target_id, target_name, summary, changes, request_id
```

`changes` is the JSON object as a string, or an empty cell when it is empty. A cell that starts with `=`, `+`,
`-`, `@`, tab or carriage return is prefixed with `'` so spreadsheets do not run
it as a formula. More than **10,000** matching rows is a **413**; narrow the
filter.

### `GET platform/audit/actions/`

```json
[{"key": "member.role_changed", "label": "Role changed", "category": "members"}]
```

Sorted by category, then key. Build the "Any action" filter from this rather
than hard-coding keys; cloud deployments register more.

### `GET platform/audit/actors/`

```json
[{"id": null, "email": "gone@acme.com", "name": "", "type": "user", "key_id": "", "key_name": ""}]
```

Actors with an event inside the retention window, including removed members
and deleted keys, so the "Anyone" filter can still find them. One entry per
identity (type, e-mail, key), named as on its newest event, so a renamed member
or key appears once. Actors without an e-mail (`system`) are left out, because
the `actor` filter cannot select them. At most 1,000, sorted by e-mail.

### Errors

Errors use the project's standard envelope (drf-standardized-errors):

```json
{"type": "validation_error", "errors": [{"code": "invalid", "detail": "Unknown action: x.y. See platform/audit/actions/.", "attr": "action"}]}
```

| Status | When |
|---|---|
| 400 | Invalid filter (unknown action, unparsable date, `from` after `to`); `attr` is the parameter name (`action` for an unknown action), or `action.<n>` when one `action` value is over 64 characters (`<n>` counts non-blank values). Blank filter values are ignored; if `actor`, `from`, `to` or `search` is repeated, its last non-blank value wins |
| 403 | Not an organisation admin, or called with a platform API key |
| 404 | List only: `page` is out of range or not a number (`code: not_found`) |
| 413 | Export matches more than 10,000 rows (`code: export_too_large`) |

## Recording events

```python
from platform_audit.actions import Action, TargetType
from platform_audit.recorder import record_platform_event

record_platform_event(
    action=Action.KEY_EXPIRY_SET,          # a registered key
    target_type=TargetType.PLATFORM_API_KEY,
    target_id=key.id,                       # stored as a string
    target_name=key.name,                   # display name at the time
    request=request,                        # actor, API key, request id, org
    changes={"before": {"expires_at": None}, "after": {"expires_at": "2027-01-01"}},
    summary="expires 2027-01-01",
)
```

Keyword-only. Also accepts `actor=` (a `User`, when there is no request),
`metadata=` (kept on the row, not returned by the read API) and
`organization=` (defaults to `UserContext`).

Rules for emitters:

1. **Call it after the change succeeded**, never before. The write is deferred
   with `transaction.on_commit`, so an event inside a transaction that rolls
   back is never stored.
2. **It never raises.** A failure is logged, without the exception's message, and the event
   is lost; the caller's request is unaffected. Code that reads a *before*
   value for an event should be wrapped with `platform_audit.recorder.best_effort`
   so that read cannot fail the request either. If it fails, pass `None` for
   that side of `changes` (the side is left out rather than stored as `null`,
   which would read as "the value was unset"); for an update, record the
   current values as `after`; end the summary with
   `recorder.BEFORE_UNAVAILABLE`.
3. **Never put secrets in `changes`, `summary` or `metadata`** — key values,
   tokens, passwords.
4. **Use a registered action.** An unregistered key is logged and dropped.
   Cloud code registers its own in `AppConfig.ready()`:
   `register_action("review_key.rotated", "Review key rotated", "keys")`.
   Re-registering a key with the same label and category is a no-op; with a
   different one it raises.
5. `target_type` is free text; reuse a `TargetType` value where one fits.
6. For a key edit, `record_key_update(target_type=..., key=..., before=...,
   after=..., request=...)` records `key.enabled`/`key.disabled` for an
   `is_active` flip and `key.changed` for any other changed field. For
   `before=None`, see its docstring.

Expected emitters outside this PR:

| Task | Action | Notes |
|---|---|---|
| PB-T04 (UN-4399) | `capability.changed` | target `capability`, id = capability key, `changes` before/after audience |
| PB-T05 (UN-4360) | `key.expiry_set` | target per key type; cloud review keys may register their own `review_key.*` actions |
| PB-T08 (UN-4318) | `execution.aborted` | target `execution`; actor is the owner or admin who aborted |

## Action vocabulary

| Key | Label | Category | Recorded by |
|---|---|---|---|
| `member.role_changed` | Role changed | members | `users/role/` POST (assign) and DELETE (remove) |
| `member.invited` | Member invited | members | `users/invite/` (successful e-mails only); target `invitation`, id = e-mail |
| `invitation.revoked` | Invitation revoked | members | `invitation/<id>/` DELETE; target name is the invitee e-mail when the IdP returns it |
| `member.removed` | Member removed | members | `users/` DELETE; summary `was <role>` (or the unconfirmed form above) |
| `group.created` | Group created | groups | `groups/` POST |
| `group.changed` | Group changed | groups | `groups/<id>/` PUT/PATCH (name or description) |
| `group.deleted` | Group deleted | groups | `groups/<id>/` DELETE |
| `group.member_added` | Added to group | groups | `groups/<id>/members/` POST; one event per user, e-mail in summary |
| `group.member_removed` | Removed from group | groups | `groups/<id>/members/<user_id>/` DELETE |
| `key.created` | Key created | keys | platform API keys, global API deployment keys, platform keys |
| `key.rotated` | Key rotated | keys | `rotate` and the platform-key `refresh` |
| `key.revoked` | Key revoked | keys | key DELETE |
| `key.enabled` | Key enabled | keys | `is_active` set true |
| `key.disabled` | Key disabled | keys | `is_active` set false; activating a platform key also records this for each key it deactivates |
| `key.changed` | Key changed | keys | any other key field |
| `key.expiry_set` | Key expiry set | keys | PB-T05 |
| `default_profile.changed` | Default changed | defaults | `adapter/default_triad/`; per member, before→after adapter names per slot |
| `platform_setting.changed` | Setting changed | settings | `organization/settings` PATCH and `notifications/settings/` PATCH, one event per changed setting |
| `capability.changed` | Capability changed | capabilities | PB-T04 |
| `execution.aborted` | Execution aborted | executions | PB-T08 |

Target types: `member`, `invitation`, `group`, `platform_api_key`,
`global_api_deployment_key`, `platform_key`, `default_profile`,
`platform_setting`, `capability`, `execution`.

Per-deployment API keys (`api_v2`) are not recorded.

## Retention

`PLATFORM_AUDIT_RETENTION_DAYS` (env, default **365**) is the default; an
organisation can override it with the `PLATFORM_AUDIT_RETENTION_DAYS`
configuration key (1–3650). An env value outside 1–3650 is treated as 3650
(fail closed). Reads ignore an override outside the range in favour of the env
default; the purge instead skips that organisation and exits non-zero, as it
does when it cannot read the override. Every read hides events older than the
cutoff.
Rows are physically deleted by

```
python manage.py purge_platform_audit_events [--dry-run] [--batch-size N]
```

Nothing schedules it: not this app, and no deployment yet. Until something
runs it, retention only hides rows, which stay in the table, so raising an
organisation's override later shows the hidden events again. Run it from cron
if storage matters or a lowered retention must be final.

## What is not recorded

Events are recorded in the OSS views where the change already succeeds. Changes
made any other way are not recorded: identity-provider or SCIM changes, cloud
staff and admin routes, Django admin, invitation acceptance, and cloud-only
features (until cloud code emits them).

Side effects that change a member's default adapter are not recorded. Among
them: creating an adapter when the member has no default of that type makes it
the default; revoking a share, or removing a co-owner who loses all access,
clears the default that pointed at that adapter; deleting an adapter clears it
for every member who had it as a default.

Activating a legacy platform key records `key.disabled` for the keys that were
active a moment before; two admins toggling keys at the same instant can make
that list miss or name the wrong key, and if reading that list fails, the
deactivated keys are not recorded.

Each invitation is recorded as the identity provider accepts it, so the ones
sent before a later one fails are kept. The role recorded is the one the
request asked for; an identity provider that coerces a missing or unknown role
(Auth0 invites those as a user) is not reflected. With `ATOMIC_REQUESTS` on,
a request that fails drops all of its events, these included.

A role change whose identity-provider sync fails part-way (Auth0 removes the
current roles, then assigns the new ones) is not recorded, even though the
member may already have lost their previous role.

Deleting a group records `group.deleted` only; the memberships it removes do
not get their own `group.member_removed` events.

Revoking an invitation makes one extra identity-provider call to resolve the
invitee e-mail; if it fails, or the invitation is not in the first page the
provider returns, the event names the invitation id instead.

The ORM refuses to update or delete an event, but foreign-key cascades still
apply (deleting a user nulls `actor.id`; deleting an organisation deletes its
events), and so does the purge. Treat this as a guard against accidental
edits, not as tamper evidence.
