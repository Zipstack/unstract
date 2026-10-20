# Frontend v1 E2E (`frontend-v1-e2e`)

Playwright suite for the v1 frontend (epic UN-4257, task P0-T09). It is kept
apart from the v0 suite in `tests/e2e/ui/`: own config, fixtures, lock and
rig group, so v1 results never mix with v0's (D10, constraint 12).

## Run

```bash
# Through the rig (boots the platform, then runs e2e-smoke first)
tox -e groups -- frontend-v1-e2e

# Standalone against a running stack
cd tests/e2e/ui-v1
bun install --frozen-lockfile
bunx playwright install chromium
UNSTRACT_FRONTEND_URL=http://localhost:3000 UNSTRACT_BACKEND_URL=http://localhost:8000 bunx playwright test

bun run lint && bun run typecheck
```

| Env | Meaning |
| --- | --- |
| `UNSTRACT_FRONTEND_URL`, `UNSTRACT_BACKEND_URL` | Stack under test (the rig exports both) |
| `UNSTRACT_AUTH_MODE` | `oss` or `auth0`; detected automatically otherwise |
| `UNSTRACT_ADMIN_USER` / `_PASSWORD` | The `admin` role (defaults to the seeded `unstract` user) |
| `UNSTRACT_E2E_<ROLE>_USER` / `_PASSWORD` | Any other role; a test asking for a role without them skips |
| `UNSTRACT_E2E_ORG_ID` | The organisation to select; the first one by default |
| `UNSTRACT_DISTRIBUTION` | `oss` (default), `cloud` or `onprem`: which tagged tests run |
| `UNSTRACT_E2E_A11Y_IMPACT` | Lowest axe impact that fails a scan; default `serious` |

## Writing a page spec

One spec per page task, named by task id: `specs/P4-T01.spec.ts`. The P8-T01
shared journeys go in `journeys/`. Every test carries a distribution tag;
untagged tests never run.

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
| `expectOldVersionRoundTrip` | Human Review (page 11) only: old-version preference on and off |

## Built ahead of P0-T03

P0-T09 is blocked by P0-T03 (version switch and route registry), which had not
landed when this harness was written. Every P0-T03 dependency goes through one
adapter, `contract/registry.ts`, and every assumed DOM marker sits in
`contract/v1-ui.ts`. To switch over when the blocking tasks land:

1. **Registry** (P0-T03): in `contract/registry.ts`, replace the stub block
   with a re-export of the frontend registry and set `REGISTRY_SOURCE` to
   `"frontend"`. The redirect and old-version self-tests then run on their
   own. The registry module has to be importable outside Vite (plain data,
   relative imports, no `import.meta.env`, no aliases or asset imports), or
   emitted as JSON.
2. **Old-version preference key** (P0-T03): set `OLD_VERSION_PREFERENCE` to
   the real storage key.
3. **v1 preview of unregistered pages** (P0-T03): set `V1_PREVIEW` to the
   dev/test-only override, and the key and route in
   `specs/harness/preview.spec.ts`.
4. **Demo route** (P0-T03): point part 2 of `specs/P0-T09.demo.spec.ts` at the
   real development-only demo route, and delete `support/demo-page.ts`.
5. **v1 root marker** (P0-T01/P0-T03): set `V1_ROOT_SELECTOR` in
   `contract/v1-ui.ts` to the v1 tree root.
6. **State components** (P1): set `STATE_TEST_IDS` to the core skeleton, empty,
   error and no-permission components.
7. **Themes** (P0-T04): swap `defaultSetTheme` in `helpers/themes.ts` for the
   real theme mechanism.
8. **a11y level** (P8-T02): confirm or change the default `serious`.
9. **Gate**: drop `optional: true` from `frontend-v1-e2e` in
   `tests/groups.yaml` once CI shows the group green.
