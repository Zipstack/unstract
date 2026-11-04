# v1 test harness

Shared helpers for v1 unit tests, imported as `@v1/test`. Only test files
(`*.test.ts(x)`, `*.spec.ts(x)`) and this folder may import it.

## Running

| Command | Runs |
| --- | --- |
| `bun run test:v1` | `vitest.v1.config.mts` (src/v1 minus `plugins/`), `vitest.v1-plugins.config.mts` (cloud v1 plugins), then the guardrail fixtures |
| `npx vitest --config vitest.v1.config.mts` | v1 in watch mode |
| `python -m tests.rig run frontend-v1-unit` | the rig group CI runs |

v0 (`bun run test`, the rig's `frontend` group) excludes `src/v1/`, so a v1
result never changes a v0 one and the reverse. Cloud v1 plugins
(`src/v1/plugins/<id>/`) run in the cloud overlay's `frontend-v1-unit-cloud`
group, never in `frontend-v1-unit`.

Each v1 config enforces its own coverage threshold, 80% on lines, statements,
functions and branches. It writes to `coverage/v1` (and `coverage/v1-plugins`)
as text summary, `json-summary` and `lcov`. A miss fails the v1 group only.
Raise the threshold in `vitest.v1.config.mts` as v1 grows. Never lower it to
land a change.

What the config does for every test (`setup.ts`):

- `globals: false`. Import `it`, `expect` and `vi` from `vitest`.
- jest-dom matchers, Testing Library cleanup, and removal of `#v1-portal`.
- `unstubGlobals`, `unstubEnvs`, `restoreMocks`. A `vi.stubGlobal`,
  `vi.stubEnv` or `vi.spyOn` is undone after each test, so tests need no
  `afterEach` for it.
- MSW handlers reset after each test, and **the test fails if it made a
  request that no handler matched** (see below).
- No v0 transforms. A missing module fails to import (v1 has no optional
  plugin imports), and `@/` does not resolve.

## Rendering

```tsx
import { screen } from "@testing-library/react";
import { makeSession, renderV1 } from "@v1/test";

const { user, queryClient, portal, session } = renderV1(<AdapterList />, {
  route: "/adapters/llm",          // MemoryRouter start; default "/"
  path: "/adapters/:type",          // mount under a pattern so useParams works
  session: makeSession({ role: "user" }), // null renders signed out
  distribution: "cloud",            // "oss" (default) | "cloud" | "onprem"
  theme: "dark",                    // "light" (default) | "dark" | "unstract"
});
await user.click(screen.getByRole("button", { name: "Add" }));
```

`renderV1` returns everything Testing Library's `render` does, plus:

- `user`: a `userEvent.setup()` instance. Pass `userEventOptions`, for example
  `{ advanceTimers: vi.advanceTimersByTime }` with fake timers.
- `queryClient`: a fresh client per render, with no retries, no refetch on
  focus and no garbage collection mid-test. Pass `queryClient` to share one.
- `portal`: the `#v1-portal` container, themed like the root.
- `session`, `distribution`, `theme`: what the test rendered with.

`renderHookV1(hook, { initialProps, ...sameOptions })` does the same for hooks.

### Providers, and swapping in the real ones

`providers.tsx` is the only file that knows the provider chain. Each slot is a
stand-in until its task lands:

| Slot | Stand-in today | Replace with, when it lands |
| --- | --- | --- |
| query | `QueryClientProvider` over `createTestQueryClient()` | the data layer's provider (P0-T05, UN-4313) |
| router | `MemoryRouter` (+ `Routes` when `path` is set) | the app router in memory mode, with the route registry (P0-T03, UN-4271) |
| theme | `div.v1[data-ui-version="v1"][data-theme]` + `#v1-portal` | `app/theme/ThemeProvider` (P0-T04, #2399). Set the theme store's preference from `context.theme` first |

To swap one, change its component in `PROVIDER_SLOTS`. It receives the
resolved `ProviderContext` (query client, route, path, session, distribution,
theme). Tests and `renderV1`'s options stay the same. When a real session
store or plugin registry exists, seed it from `context.session` and
`context.distribution` in the same file.

## Network

Every HTTP request (fetch and XHR, so axios too) and every WebSocket goes
through MSW. Register handlers per test with `mockApi` (`http.*` for HTTP,
`ws.link(url)` for sockets). They are dropped after the test.

```ts
import { apiPath, DEFAULT_SESSION, HttpResponse, http, mockApi } from "@v1/test";

mockApi(
  http.get<never, never, Adapter[]>(apiPath(DEFAULT_SESSION, "/adapter/"), () =>
    HttpResponse.json(adapterFixtures.list),
  ),
);
```

`apiPath(session, "/adapter/")` builds the org-scoped
`/api/v1/unstract/<org id>/adapter/`.

**An unmocked request fails the test**, even when the code under test catches
the error. An HTTP request gets a network error and a WebSocket is closed
(code 1011), so nothing leaves the process. The test then fails with:

```text
Error: Unmocked request (add a handler with mockApi() or server.use()):
  GET http://localhost:3000/api/v1/unstract/org-1/adapter/?adapter_type=LLM
```

This covers requests made after the last assertion too. Ones started by an
unmount effect fail the test that unmounted. Ones made after a file's last test
(a timer firing during its `afterAll`) fail the file. Catch-all handlers do
this, and they always match last, even after `server.resetHandlers(...)` with
arguments. A test that leaves fake timers on gets real timers back after it.

### Typed fixtures per service module

Each service module in `services/` exports its request and response types.
Its fixtures live in `test/fixtures/<service>.ts`, typed against those types
so a contract change breaks the fixture at typecheck:

```ts
// test/fixtures/adapters.ts
import type { Adapter } from "@v1/services/adapters";
import { apiPath, HttpResponse, http, type TestSession } from "@v1/test";

export const adapterFixtures = {
  list: [{ id: "a1", adapter_name: "OpenAI", adapter_type: "LLM" }],
} satisfies Record<string, Adapter[]>;

export const adapterHandlers = (session: TestSession) => [
  http.get<never, never, Adapter[]>(apiPath(session, "/adapter/"), () =>
    HttpResponse.json(adapterFixtures.list),
  ),
];
```

## Accessibility

```ts
await expect(container).toHaveNoA11yViolations();
await expectNoA11yViolations(screen.getByRole("dialog"));
const violations = await axeViolations(container); // inspect them yourself
```

These run axe-core. A failure lists each node as `[rule] (impact) selector:
help`, with the rule's URL. `color-contrast` is off (tests load no CSS) and so
is `region` (a component rendered alone is outside a page's landmarks). Pass
`{ rules: { region: { enabled: true } } }` for a whole-page test. Always
`await` the matcher.

## Browser APIs happy-dom does not drive

```ts
const size = installResizeObserver();
size.resize(element, { width: 640, height: 480 });

const view = installIntersectionObserver();
view.intersect(element, true);

const media = mockMatchMedia({ dark: false });
media.setDark(true); // fires (prefers-color-scheme: dark) listeners
```

Each wraps its callbacks in `act()` and is undone after the test.

## Proof the harness fails when it should

`test-fixtures/v1-harness/` runs real vitest processes, under `node --test` in
`bun run test:v1`. The known-bad cases are an unmocked fetch, XHR and
WebSocket, a request on unmount (and which test it fails), a request after the
last test, and `resetHandlers` with arguments. The known-good cases are a mocked
fetch and fake timers left on.
