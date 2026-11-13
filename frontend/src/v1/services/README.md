# Services: the v1 data layer

One way to call the backend (P0-T05). Pages read and write server state through
TanStack Query with the typed functions here, and never write their own loading
or error handling.

## Files

| File | Holds |
| --- | --- |
| `http.ts` | The one HTTP client, and `orgPath()`. Adds `X-CSRFToken` (from the `csrftoken` cookie) to same-origin POST, PUT, PATCH and DELETE, and a new `X-Request-ID` to every request; rejects with an `ApiError`; treats the auth middleware's 401 as session expiry, once per page load, so concurrent 401s redirect once. Only `services/` and `plugins/<plugin>/services/` import it, or axios, or call `fetch`, `XMLHttpRequest` or `EventSource` (`lint:v1`). |
| `context.ts` | What the client takes from the session: `setOrganizationId()` (the org `orgPath()` uses) and `onSessionExpired()` (default: v0's `/api/v1/logout` redirect; a handler must leave the page). The session (P0-T06, UN-4314) sets both. |
| `errors.ts` | `ApiError`, `toApiError()`, `isCancelled()`, `mapFieldErrors()`. |
| `report.ts` | `reportApiError()`: a toast through `notify()`, or a log line with the request id. |
| `page.ts` | `Page<T>` (the backend's `{count, next, previous, results}`), `PageParams`, `pageQuery()` and `previousPageInOrg()`. |
| `<resource>.ts` | One module per backend resource, e.g. `adapters.ts`. |

## Writing a service module

- Backend URLs appear only here (`lint:v1`). Build org-scoped ones with
  `orgPath("/adapter/", org)`, which gives `/api/v1/unstract/<org>/adapter/`,
  and write the trailing slash exactly as the backend route has it. A cloud
  plugin keeps its service modules in `plugins/<plugin>/services/`.
- Every function takes typed params and `RequestOptions` (`{ signal, org }`),
  passes the signal to the client and the org to `orgPath()`, and returns a
  typed response. Never accept a free-form query object. A call outside an
  organisation (`organizations.ts`, `session.ts`) takes only `{ signal }`.
- A paged endpoint takes `PageParams` (`page` from 1, `pageSize`), sends them
  with `pageQuery()`, and returns `Page<T>`. Its query sets
  `placeholderData: previousPageInOrg(queryKey)`, so the previous page stays on
  screen while the next loads, but never another organisation's (see
  `adapterQueries.page`). A page past the end is a 404 ("Invalid page."), so
  whoever holds the page number steps back to the last page,
  `Math.max(1, Math.ceil(count / pageSize))`, after a delete.
- Export query keys and options per resource. Keys are
  `[org, resource, "list" | "page" | "detail", params | id]`, and each query
  fetches for the org in its key, so two organisations never share a cache
  entry:

```ts
export const adapterKeys = {
  all: () => [currentOrganizationId(), "adapters"] as const,
  list: (params: ListAdaptersParams) => [...adapterKeys.all(), "list", params] as const,
};
export const adapterQueries = {
  list: (params: ListAdaptersParams) =>
    queryOptions({
      queryKey: adapterKeys.list(params),
      queryFn: ({ queryKey: [org], signal }) => listAdapters(params, { signal, org }),
    }),
};
```

- Invalidate a resource with `queryClient.invalidateQueries({ queryKey: adapterKeys.all() })`.
- Fixtures go in `test/fixtures/<resource>.ts`, typed against the module's types
  (see `test/fixtures/adapters.ts`).

## Errors

Every failure becomes an `ApiError` with `kind`, `message` (for people),
`status`, `fieldErrors`, `formErrors` and `requestId`. A cancelled request
rejects with axios's `CanceledError` instead; check `isCancelled()` first
(`toApiError()` calls it `unknown`, "The request was cancelled.").
`organizations.ts` turns a 412 on the list and a 403 on set into an
`OrganizationError` for the switcher, with the `ApiError` as its `cause` and
its `requestId`.
A download (`responseType: "blob"`) gets its error body as a Blob, which is not
read: its 401 is session expiry and its 402 `subscription`. The first v1
download service makes `http.ts` parse JSON Blob errors, with a test.

| Kind | When |
| --- | --- |
| `validation` | `type: "validation_error"` (400); fields in `fieldErrors`, the rest in `formErrors` |
| `subscription` | A `subscription_error` / `subscription_inactive` type or code, or a 402 with no `type`; a provider's typed 402 (`sdk_error`) is `client` |
| `unauthenticated` | The auth middleware's 401 (no `type` in the body); a typed 401, such as a provider rejecting its key, is `client` |
| `forbidden` | 403 |
| `not_found` | 404 |
| `client` | Any other 4xx |
| `server` | 5xx |
| `network` | No response |
| `unknown` | Anything that is not an HTTP failure |

## How failures reach the user

`app/query.ts` reports every failure once, so pages do not:

| Failure | Shown as |
| --- | --- |
| Mutation | A toast with the request id. Pass `meta: { notify: false }` when the form shows it; it is then logged. |
| Read whose first fetch fails (also a next page) | Inline, by `QueryView` (`components/patterns/`): an `InlineAlert` with Retry and the request id, after a skeleton (or, for a next page, the previous page). Also logged. |
| Refresh that fails while the query's data is on screen | A toast, replaced rather than stacked while the same query keeps failing. Every query that cannot reach the server shares one toast. |
| A `select` that throws | The page's error boundary once no fetch is in flight: it is a bug, not a failed request. |
| 401 | One redirect to sign in; no toast. |
| Subscription | A toast that stays until dismissed; inline like any other first-fetch failure. |
| Cancellation | Nothing. |

Reads retry twice on a network error, 502, 503 or 504. Mutations never retry.
Offline, requests still go out (`networkMode: "always"`) and fail as
`network`; nothing waits for the connection, and a save is never sent later.
Reads refetch when the connection returns.

## Forms

```ts
const save = useMutation({ mutationFn: createAdapter, meta: { notify: false } });
const { fields, form } = mapFieldErrors(save.error, ["adapter_name", "description"]);
```

`fields` holds one message per field the form shows. `form` holds everything
else, including errors for fields the form does not show, for one
`InlineAlert` above the form; nothing is dropped. Before the first submit
(`error` is null) or after a cancel, both are empty.
