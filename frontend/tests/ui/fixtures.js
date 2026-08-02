import { expect, test as base } from "@playwright/test";

/**
 * Shared fixtures for the `ui` group.
 *
 * Every page in this app is behind login AND org-scoped (`/<orgId>/<route>`),
 * so a spec that just calls `page.goto("/dashboard")` lands on the login screen
 * and asserts nothing useful. This module does the handshake once per worker
 * and exposes an `app` helper that resolves org-relative paths.
 *
 * The login flow mirrors `tests/e2e/conftest.py::authed_session` deliberately —
 * form POST to /api/v1/login, then GET /organization to seed the CSRF cookie,
 * then POST /organization/{id}/set. Keeping the two in step means a change to
 * the auth flow breaks both suites together rather than silently skipping this
 * one.
 */

const BACKEND =
  process.env.UNSTRACT_BACKEND_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

/**
 * Log in through the API and set the active organization.
 *
 * Returns the org id, which every app route is prefixed with. Returns null when
 * the platform is unreachable or the credentials are rejected, so specs can
 * skip rather than fail — the `ui` group is `optional` precisely so a machine
 * without a running stack does not gate a build.
 */
async function authenticate(context) {
  const username = process.env.UNSTRACT_ADMIN_USER ?? "unstract";
  const password = process.env.UNSTRACT_ADMIN_PASSWORD ?? "unstract";

  let login;
  try {
    login = await context.request.post(`${BACKEND}/api/v1/login`, {
      form: { username, password },
      maxRedirects: 0,
      failOnStatusCode: false,
    });
  } catch {
    return null; // platform not reachable
  }
  // A 200 here means the login form re-rendered: bad credentials.
  if (login.status() !== 302) {
    return null;
  }

  const orgs = await context.request.get(`${BACKEND}/api/v1/organization`, {
    failOnStatusCode: false,
  });
  if (!orgs.ok()) {
    return null;
  }
  const orgId = (await orgs.json())?.organizations?.[0]?.id;
  if (!orgId) {
    return null;
  }

  const csrf = (await context.cookies())
    .find((c) => c.name === "csrftoken")
    ?.value;
  await context.request.post(`${BACKEND}/api/v1/organization/${orgId}/set`, {
    headers: csrf ? { "X-CSRFToken": csrf } : {},
    failOnStatusCode: false,
  });
  return orgId;
}

export const test = base.extend({
  /**
   * `app.goto(route)` — navigate to an org-scoped route, or skip the test when
   * no platform is available.
   */
  app: async ({ page, context }, use) => {
    const orgId = await authenticate(context);
    await use({
      orgId,
      async goto(route) {
        test.skip(
          !orgId,
          `no authenticated platform at ${BACKEND}; set UNSTRACT_BACKEND_URL ` +
            "and run the stack, or let the rig boot it (`tests.rig run ui`)",
        );
        const response = await page.goto(`/${orgId}/${route}`, {
          waitUntil: "domcontentloaded",
        });
        // The SPA renders after hydration; wait for the shell rather than a
        // fixed timeout so slow CI doesn't flake.
        await page.waitForLoadState("networkidle").catch(() => {});
        return response;
      },
    });
  },
});

export { expect };

/**
 * Assert the document does not scroll horizontally.
 *
 * The single most valuable check this tier adds: jsdom reports every element as
 * 0x0, so the `frontend` vitest group structurally cannot catch overflow. A
 * real regression this guards — `.deployment-alert` was `w-full` plus 24px side
 * margins, overflowing `.agency-layout` by exactly 48px on every workflow page.
 */
export async function expectNoHorizontalOverflow(page, what) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - window.innerWidth,
  );
  expect(overflow, `${what} overflows its viewport horizontally`).toBeLessThanOrEqual(0);
}

/**
 * Assert every element in `selector` shares a horizontal centre line.
 *
 * Guards the alignment class of bug this migration kept producing: antd
 * controls were inline-block and the shadcn equivalents are block-level, so
 * unstyled wrappers silently stopped laying out in a row. The doc-manager
 * toolbar drifted 5.6px this way; the reference measured 0.8px.
 */
export async function expectSharedBaseline(page, selector, tolerance = 2) {
  const mids = await page.$$eval(selector, (els) =>
    els
      .filter((e) => e.getBoundingClientRect().height > 0)
      .map((e) => {
        const r = e.getBoundingClientRect();
        return r.top + r.height / 2;
      }),
  );
  if (mids.length < 2) {
    return; // nothing to compare
  }
  const spread = Math.max(...mids) - Math.min(...mids);
  expect(
    spread,
    `${selector} does not share a baseline (spread ${spread.toFixed(1)}px)`,
  ).toBeLessThanOrEqual(tolerance);
}
