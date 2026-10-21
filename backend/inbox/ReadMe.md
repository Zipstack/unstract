# inbox

## Inbox contract

Each user has one inbox per organization. Paths are organization-scoped: `/api/v1/unstract/<org_id>/notifications/inbox/...`. The typed contract is the `@extend_schema` annotation on `inbox/views.py` (operation ids `inbox_list`, `inbox_read`, `inbox_read_all`). It is not part of the published deployment API spec. The item shape is provisional until it is agreed with the LLMWhisperer notifications.

| Method and path | Response |
|---|---|
| GET `notifications/inbox/` | `{count, next, previous, results, unread_count}`, newest first, `?page` and `?page_size` |
| POST `notifications/inbox/<id>/read/` | 204; 404 when the item is not the caller's |
| POST `notifications/inbox/read-all/` | 204 |

### Item

- `id`: UUID.
- `kind`: a string, today `resource_shared` or `execution_failed`. Clients show an unknown kind generically.
- `title`, `body`: display text; `body` may be empty.
- `route`: `{key, params}`, the shape global search uses (`global_search/README.md`), or null when there is nothing to open. `params` values are strings. Clients treat an unknown `key` like null. The keys the inbox sends:

| `key` | `params` | Sent for |
|---|---|---|
| `workflow.detail` | `id` | a shared workflow |
| `etl_pipeline.detail`, `task_pipeline.detail` | `id` | a shared ETL or task pipeline; other pipeline types send null |
| `api_deployment.detail` | `id` | a shared API deployment |
| `connector.detail` | `id` | a shared connector |
| `adapter.info` | `id`, `adapter_type` | a shared adapter (shared users are viewers, so the read-only page) |
| `prompt_studio_project.detail` | `id` | a shared Prompt Studio project |
| `agentic_project.detail` | `id` | a shared Agentic Studio project (cloud); not in global search |
| `execution.detail` | `id`, the run's id | a failed run; not in global search |

A shared look-up sends null.
- `created`: when the item was added.
- `read`: whether the user has read it.

### Rules

- A user sees only their own items in the current organization.
- Each event adds at most one item per user.
- `resource_shared`: a resource is shared with the user directly or with a group they belong to. The person who shared it is not notified, and neither is anyone who could already open the resource (as an owner, a direct user, a member of a group it was already shared with, or an organization admin). A resource shared with the whole organization still notifies the people it is shared with.
- `execution_failed`: a run ends with status ERROR or STOPPED, or completes with failed files, the rule the failure notifications in `notification_v2` use. The owners and co-owners of the pipeline or API deployment that ran are notified, or of the workflow for a run started from the workflow. The run records no user, so nobody else is. The body is the run's error message, and `route` is `execution.detail` with the run's id. One item per run, however often its status is written. A run marked ERROR and then corrected to a clean COMPLETED has its item withdrawn. A new `execution_failed` item does not push the live count; it shows on the next list call.
- Items are deleted 90 days after they are created, read or not, on deployments that run the PG scheduler. It runs `inbox.purge` daily at 02:30 UTC from row `inbox_purge`, which migration 0002 seeds inert and `converge_pg_scheduler --periodics` adopts; the task calls the internal endpoint `POST /internal/v1/inbox/purge/`, which deletes in batches of 5,000. Where that row is not adopted, or ownership is released, nothing purges.
- The existing e-mail and webhook notifications in `notification_v2` are separate and unchanged.

### Live unread count

A signed-in browser's Socket.IO connection also joins the room `user:<user id>`. When the user's unread count changes through a new `resource_shared` item, a read or a read-all, the backend emits `inbox:unread` to that room with `{"data": {"organization_id": "...", "unread_count": 3}}`. The count is for that organization only; a client in another organization ignores it. A failed emit is logged; the list endpoint's `unread_count` stays the source of truth.
