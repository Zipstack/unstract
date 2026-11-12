# Services: the v1 data layer

One way to call the backend (P0-T05). Pages read and write server state through
TanStack Query with the typed functions here, and never write their own loading
or error handling.

## Files

| File | Holds |
| --- | --- |
| `http.ts` | The one HTTP client. Adds `X-CSRFToken` (from the `csrftoken` cookie) to same-origin POST, PUT, PATCH and DELETE, and a new `X-Request-ID` to every request; rejects with an `ApiError`; treats a 401 as session expiry, once for any number of concurrent 401s. Only `services/` imports it, or axios (`lint:v1`). |
| `context.ts` | What the client takes from the session: `setOrganizationId()` (org-scoped paths) and `onSessionExpired()` (default: v0's `/api/v1/logout` redirect). The session (P0-T06, UN-4314) sets both. |
| `errors.ts` | `ApiError`, `toApiError()`, `isCancelled()`, `mapFieldErrors()`. |
| `report.ts` | `reportApiError()`: a toast through `notify()`, or a log line with the request id. |
| `page.ts` | `Page<T>` (the backend's `{count, next, previous, results}`), `PageParams` and `pageQuery()`. |
| `<resource>.ts` | One module per backend resource, e.g. `adapters.ts`. |

## Writing a service module

- Backend URLs appear only here (`lint:v1`). Build org-scoped ones with
  `orgPath("/adapter/")`, which gives `/api/v1/unstract/<org>/adapter/`, and
  write the trailing slash exactly as the backend route has it.
- Every function takes typed params and `RequestOptions` (`{ signal }`), passes
  the signal to the client, and returns a typed response. Never accept a
  free-form query object.
- A paged endpoint takes `PageParams` (`page` from 1, `pageSize`), sends them
  with `pageQuery()`, and returns `Page<T>`. Its query sets
  `placeholderData: keepPreviousData`, so the previous page stays on screen
  while the next loads (see `adapterQueries.page`).
- Export query keys and options per resource. Keys are
  `[org, resource, "list" | "page" | "detail", params | id]`, so two
  organisations never share a cache entry:

```ts
export const adapterKeys = {
  all: () => [currentOrganizationId(), "adapters"] as const,
  list: (params: ListAdaptersParams) => [...adapterKeys.all(), "list", params] as const,
};
export const adapterQueries = {
  list: (params: ListAdaptersParams) =>
    queryOptions({
      queryKey: adapterKeys.list(params),
      queryFn: ({ signal }) => listAdapters(params, { signal }),
    }),
};
```

- Invalidate a resource with `queryClient.invalidateQueries({ queryKey: adapterKeys.all() })`.
- Fixtures go in `test/fixtures/<resource>.ts`, typed against the module's types
  (see `test/fixtures/adapters.ts`).

## Errors

Every failure becomes an `ApiError` with `kind`, `message` (for people),
`status`, `fieldErrors`, `formErrors` and `requestId`. A cancelled request
rejects with axios's `CanceledError` instead; check `isCancelled()` first.

| Kind | When |
| --- | --- |
| `validation` | `type: "validation_error"` (400); fields in `fieldErrors`, the rest in `formErrors` |
| `subscription` | 402, or a `subscription_error` / `subscription_inactive` body |
| `unauthenticated` | 401 |
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
| Read with no data yet | Inline, by `QueryView` (`components/patterns/`): a skeleton, then an `InlineAlert` with Retry and the request id. Also logged. |
| Read that fails while data is on screen | A toast, replaced rather than stacked while the same query keeps failing. |
| 401 | One redirect to sign in; no toast. |
| Subscription | A toast that stays until dismissed. |
| Cancellation | Nothing. |

Reads retry twice on a network error, 502, 503 or 504. Mutations never retry.

## Forms

```ts
const save = useMutation({ mutationFn: createAdapter, meta: { notify: false } });
const { fields, form } = mapFieldErrors(save.error, ["adapter_name", "description"]);
```

`fields` holds one message per field the form shows. `form` holds everything
else, including errors for fields the form does not show, for one
`InlineAlert` above the form; nothing is dropped.
