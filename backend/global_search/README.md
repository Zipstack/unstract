# Global search

One endpoint that finds anything the caller can open, grouped by type. This
file is the published contract for consumers: P2-T10, the top-bar search
panel, and PB-T18, the portal search, which shares the envelope. The
response JSON Schema is
[`contract/search-response.schema.json`](contract/search-response.schema.json);
tests validate real responses against it and check the type table's order,
type, label and route.key columns against the registered providers.

## Endpoint

```
GET /api/v1/unstract/{org_id}/search/?q=<text>&types=<csv>&limit=<n>
```

Authentication uses the session auth stack shared by the other tenant
endpoints. Service accounts get the same visibility rules their `for_user()`
gives them in each list. The endpoint is additive: no existing endpoint
changes.

## Parameters

| param | default | rules |
|---|---|---|
| `q` | `""` | Trimmed. After trimming, **fewer than 2 characters returns 200 with `groups: []`**. More than 100 characters returns 400. Matches name and description case-insensitively; `%` and `_` match literally. |
| `types` | all | Comma-separated type keys. Unknown or unavailable keys are **ignored**, so one panel can send cloud keys to an OSS backend. |
| `limit` | `5` | Results per type, 1 to 20. A non-integer or out-of-range value returns 400. |

## Response

```json
{
  "query": "invoice",
  "groups": [
    {
      "type": "prompt_studio_project",
      "label": "Prompt Studio projects",
      "has_more": true,
      "results": [
        {
          "type": "prompt_studio_project",
          "id": "6f1c2a4e-1d1b-4c8e-9a51-0c7b2f1e9d10",
          "name": "Invoice parser",
          "context": "alice@acme.com",
          "match": "name_prefix",
          "route": {
            "key": "prompt_studio_project.detail",
            "params": {"id": "6f1c2a4e-1d1b-4c8e-9a51-0c7b2f1e9d10"}
          }
        }
      ]
    }
  ],
  "failed_types": []
}
```

- Groups are returned in the `order` of the table below. **Empty groups are
  omitted.**
- `has_more` is true when the type has more matches than `limit`. There is
  no total count; the "More" link opens the type's own list.
- `match` names the tier that ranked the result. Results are sorted by tier
  (`name_prefix`, `name`, `description_prefix`, `description`), then by most
  recently modified, then by id.
- `context` is a single display-only line, or `null`. Do not parse it.
- `route.key` is a route-registry name, not a URL. `route.params` values are
  strings. It is one of the keys the table below lists for the result's
  type; adapters have two (see below the table). A client that does not
  know a key should render the result without a link, never guess a
  screen.
- `type` is an open string. A client should render an unknown type with its
  `label`, or skip it.
- `failed_types` lists types whose search failed; their groups are missing
  even if they have matches, so a client can say "some results could not be
  loaded". It is empty on a normal response.
- Every result has a `route`, and `route.params` always includes `id`: a
  search result is always one item that can be opened. Other contracts that
  reuse the route object (for example the notifications inbox, PB-T17) may
  set `route` to `null` when an item has nothing to open; search never does.
  Clients treat a `null` route like an unknown key: render without a link.

Errors use the standard error envelope:

- `400 {"type": "validation_error", "errors": [{"code", "detail", "attr"}]}`
  for bad parameters.
- `503` with code `search_unavailable` when every searched type failed with
  a database error a retry may clear (unreachable, timed out, locked), or
  when a failure left the connection unusable (even if other types had
  already answered). Safe to retry; never show it as "no results". A slow or
  locked query on a healthy connection otherwise only drops its own type
  into `failed_types` while other types still answer.
- `500` with code `search_failed` when every searched type failed and not
  all with such database errors (a bug). Retrying will not help.
- 401 and 403 behave as on every tenant endpoint.

### No matches

When nothing matches, the response is still 200, with no groups:

```json
{"query": "zzqx", "groups": [], "failed_types": []}
```

A query shorter than 2 characters returns the same shape. A panel shows
"No results" here. If `failed_types` is non-empty while `groups` is empty,
some types could not be searched, so the panel says that instead of plain
"No results". When every searched type fails, the response is a 5xx, not an
empty 200 (see the errors above).

## Types

| order | type | label | route.key | route.params | context |
|---|---|---|---|---|---|
| 10 | `prompt_studio_project` | Prompt Studio projects | `prompt_studio_project.detail` | `id` | owner e-mail |
| 30 | `workflow` | Workflows | `workflow.detail` | `id` | owner e-mail |
| 40 | `api_deployment` | API deployments | `api_deployment.detail` | `id` | parent workflow name |
| 50 | `etl_pipeline` | ETL pipelines | `etl_pipeline.detail` | `id` | parent workflow name |
| 60 | `task_pipeline` | Task pipelines | `task_pipeline.detail` | `id` | parent workflow name |
| 80 | `adapter` | Adapters | `adapter.detail` / `adapter.info` | `id`, `adapter_type` | adapter type · provider |
| 90 | `connector` | Connectors | `connector.detail` | `id` | provider |

An adapter opens on `adapter.detail` only for a caller who may edit it
(owner or co-owner, org admin, service account), the same rule as the
adapter `retrieve` endpoint. Everyone else gets `adapter.info`, with the
same params, a read-only view backed by `adapter/info/<id>/`, which allows
every caller search sends there.

Cloud and on-prem add `agentic_project` (20) and `review_queue` (70). Those
apps register these types themselves, and they are documented in the cloud
repo.

### What is matched and who sees it

Each type starts from the same `for_user()` queryset its list view uses.
That covers owners, co-owners, direct viewers, group shares, org shares,
admins and service accounts. Search rules:

- Names matched: `tool_name`, `workflow_name`, `display_name` and
  `api_name`, `pipeline_name`, `adapter_name`, `connector_name`.
- Descriptions matched: Prompt Studio projects, workflows, API deployments
  and adapters. Pipelines and connectors have no description.
- Pipelines: ETL and Task only. DEFAULT and APP pipelines are excluded.
- Adapters: platform-provided (frictionless) adapters are never returned.
  The adapter list shows them so any member can delete one, but nobody can
  open their detail view. No Op adapters are never returned either.
- Owner e-mail is not matched. The workflow, Prompt Studio, adapter and
  connector list `search` parameters do match it, so the panel and those
  filtered lists can differ slightly.

## Response-time budget

**p95 ≤ 300 ms server time for all types at `limit=5`**, on an organisation
of the largest current size. The fixture used is 2,000 rows per type, 200
users and 20 groups; it will be updated when real largest-org counts are
available.

CI does not gate on latency, because runners are shared. `tests/test_budget.py`
gates on query count instead: a request may issue at most three SQL queries
per type in total (one ranked search per type, plus the organisation point
lookups the existing `for_user()` makes) plus a small fixed overhead, and
the count must not change between `limit=1` and `limit=20`, so an N+1 query
pattern fails the test. The measured p95 is printed on every run and is
asserted only with `GLOBAL_SEARCH_ASSERT_P95=1`, against
`GLOBAL_SEARCH_CEILING_MS` (default 300). No trigram index is used: every
query is filtered by organisation first.

## Adding a type

Subclass `global_search.providers.SearchProvider`, or use
`ModelSearchProvider` for a single queryset. It must apply the type's own
list visibility rule. Register it with
`global_search.registry.register_provider()` from the owning app's
`AppConfig.ready()`, add a row to the table above, and add visibility tests.
