# Frontend v1 E2E (`frontend-v1-e2e`)

Playwright suite for the v1 frontend (epic UN-4257, task P0-T09). It is kept
apart from the v0 suite in `tests/e2e/ui/`: own config, fixtures, lock and
rig group, so v1 results never mix with v0's (D10, constraint 12).

## Run

```bash
# Once: the suite's own dependencies and a browser. The group gates the
# build, so without these the rig reports it red, not skipped.
cd tests/e2e/ui-v1
bun install --frozen-lockfile
bunx playwright install chromium

# Through the rig, as CI runs it (boots the platform, e2e-smoke first).
# The stack needs a frontend image built with VITE_V1_DEV_ROUTES=true, as
# ci-test.yaml builds it; a release image has no demo pages.
tox -e e2e

# Standalone against a running stack
UNSTRACT_FRONTEND_URL=http://localhost:3000 UNSTRACT_BACKEND_URL=http://localhost:8000 bunx playwright test

bun run lint && bun run typecheck
```

| Env | Meaning |
| --- | --- |
| `UNSTRACT_FRONTEND_URL`, `UNSTRACT_BACKEND_URL` | Stack under test (the rig exports both) |
| `UNSTRACT_AUTH_MODE` | `oss` or `auth0`; detected automatically otherwise |
| `UNSTRACT_ADMIN_USER` / `_PASSWORD` | The `admin` role (defaults to the seeded `unstract` user) |
| `UNSTRACT_E2E_<ROLE>_USER` / `_PASSWORD` | Any other role, upper-cased with non-alphanumerics as `_` (`org-admin` reads `UNSTRACT_E2E_ORG_ADMIN_USER`); a test asking for a role without them skips, and fails under the rig, which seeds only the admin |
| `UNSTRACT_E2E_ORG_ID` | The organisation to select; the first one by default |
| `UNSTRACT_DISTRIBUTION` | `oss` (default), `cloud` or `onprem`: tests tagged for it run. Must match the image's `VITE_DISTRIBUTION` (unset builds as oss), which decides the pages it renders |
| `UNSTRACT_E2E_A11Y_IMPACT` | Lowest axe impact that fails a scan; default `serious` |

## Writing a page spec

One spec per page task, named by task id: `specs/P4-T01.spec.ts`. The P8-T01
shared journeys go in `journeys/`. Every test carries a distribution tag: a
test tagged only for another distribution is not collected (nor are its
hooks), and one with no distribution tag (or a mistyped one, `@OSS`) fails.

The stack under test is the E2E image: built with `VITE_V1_DEV_ROUTES=true`
(ci-test.yaml), which registers P0-T03's demo pages and honours the preview
override. A release image ignores both.

```ts
import { DIST, expect, test } from "../fixtures/index.ts";
import { expectAccessible, expectFiveStates, forEachTheme } from "../helpers/index.ts";

test.describe("P4-T01 API Deployments", { tag: DIST.both }, () => {
  // Non-final task of a multi-task page: render v1 before registration (D9).
  test.use({ v1Preview: ["UN06"] });

  test("five states", async ({ page, app }) => {
    await expectFiveStates(page, {
      open: () => app.goto("api"),
      api: "**/api/v1/unstract/*/api/deployment/**",
      rest: (p) => p.getByRole("table"),
      emptyBody: [],
    });
  });

  test("accessible in every theme", async ({ page, app, seed }) => {
    await seed.create("workflow/", { workflow_name: seed.name("wf") });
    await forEachTheme(page, async (theme) => {
      await app.goto("api");
      await expectAccessible(page, { label: theme });
    });
  });
});
```

| Fixture or helper | Does |
| --- | --- |
| `session`, `app`, `role` | Signs in as a seeded user of a role, selects the org; `app.goto(route)` opens org-scoped routes |
| `seed` | Creates rows through the API and deletes them after the test |
| `v1Preview` | Renders an unregistered page's v1 routes (non-final page tasks) |
| `DIST` / `TAG` | Marks a test as OSS, cloud, on-prem or several |
| `expectFiveStates` | Drives rest, loading, empty, error and no-permission by intercepting the screen's API |
| `expectAccessible` | axe scan, WCAG 2.0/2.1 A+AA, fails at or above the impact level |
| `forEachTheme` | Repeats a check in Light, Dark and Unstract |
| `expectV0RedirectsToV1` | A v0 URL lands on the mapped v1 route |
| `expectOldVersionRoundTrip` | Toggle pages only (Human Review, page 11, and its demo stand-in): old-version preference on and off, for `session.userId` |

## Where the harness meets the frontend

- `contract/registry.ts` reads P0-T03's registry data from the frontend
  (`src/v1/app/registry/{types,entries,validate}.ts`, `src/v1/lib/oldVersion.ts`),
  which import nothing Vite-specific. `REGISTRY` is what the E2E image renders
  as v1: registered pages plus the demo pages. The typecheck in CI holds the
  harness to those types.
- `contract/v1-ui.ts` holds the DOM markers: the v1 root
  (`[data-ui-version="v1"]`, carrying `data-theme`), and the theme modes and
  storage key from `src/v1/lib/theme.ts`.
- `specs/P0-T09.demo.spec.ts` proves the switch on P0-T03's demo pages
  (`/:orgName/v1-demo`, `/:orgName/v1-demo-review`). Those pages load no data,
  so the five-state helper is proven on `support/state-fixture.ts`.

Still open:

1. **State components** (P1): set `STATE_TEST_IDS` to the core skeleton, empty,
   error and no-permission components, following the team's selector decision
   for v1 tests.
2. **a11y level** (P8-T02): confirm or change the default `serious`.
