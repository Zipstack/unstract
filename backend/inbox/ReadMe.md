# inbox

## Inbox contract

Each user has one inbox per organization. Paths are organization-scoped: `/api/v1/unstract/<org_id>/notifications/inbox/...`. The typed contract is the `@extend_schema` annotation on `inbox/views.py` (operation ids `inbox_list`, `inbox_read`, `inbox_read_all`). It is not part of the published deployment API spec. The item shape is provisional until it is agreed with the LLMWhisperer notifications (PB-T18).

| Method and path | Response |
|---|---|
| GET `notifications/inbox/` | `{count, next, previous, results, unread_count}`, newest first, `?page` and `?page_size` |
| POST `notifications/inbox/<id>/read/` | 204; 404 when the item is not the caller's |
| POST `notifications/inbox/read-all/` | 204 |

### Item

- `id`: UUID.
- `kind`: `resource_shared` or `execution_failed`. Clients show an unknown kind generically.
- `title`, `body`: display text; `body` may be empty.
- `route`: `{key, params}` as in global search (`global_search/README.md`), or null when there is nothing to open. Clients treat an unknown `key` like null.
- `created`: when the item was added.
- `read`: whether the user has read it.

### Rules

- A user sees only their own items in the current organization.
- Each event adds at most one item per user.
- `resource_shared`: a resource is shared with the user directly or with a group they belong to. The person who shared it is not notified, and users who already had direct access are not notified again.
- `execution_failed`: a run ends with status ERROR or STOPPED, or completes with failed files, the rule the failure notifications in `notification_v2` use. The owners and co-owners of the pipeline or API deployment that ran are notified, or of the workflow for a run started from the workflow. The run records no user, so nobody else is. The body is the run's error message. One item per run, however often its status is written.
- The existing e-mail and webhook notifications in `notification_v2` are separate and unchanged.

### Live unread count

A signed-in browser's Socket.IO connection also joins the room `user:<user id>`. Whenever the user's unread count changes (a new item, read, read all), the backend emits `inbox:unread` to that room with `{"data": {"organization_id": "...", "unread_count": 3}}`. The count is for that organization only; a client in another organization ignores it. A failed emit is logged; the list endpoint's `unread_count` stays the source of truth.
