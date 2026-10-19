import { expect, test as base } from "@playwright/test";

/**
 * Shared fixtures for the `ui` rig group.
 *
 * Every page is behind login AND org-scoped (`/<orgId>/<route>`), so a spec
 * that calls `page.goto("/dashboard")` lands on the login screen and asserts
 * nothing. This module performs the handshake once per worker and exposes an
 * `app` helper that resolves org-relative paths.
 *
 * TWO auth modes, because the suite has to run against both deployments:
 *
 *   oss    Django mock-login. Form POST to /api/v1/login, then the org
 *          handshake. Mirrors tests/e2e/conftest.py::authed_session
 *          deliberately — a change to that flow breaks both suites together
 *          rather than silently skipping this one.
 *
 *   auth0  Enterprise. The IdP owns the credential exchange, so there is no
 *          API to POST to. Drive the hosted login form in the browser, then
 *          let the app complete its own callback.
 *
 * Selected by UNSTRACT_AUTH_MODE, or auto-detected: a backend that answers
 * /api/v1/login with a 302 *and* then serves /api/v1/organization is OSS;
 * anything else is treated as auth0. Auto-detection matters because dev and CI
 * differ and neither should need a bespoke invocation.
 */

const BACKEND =
  process.env.UNSTRACT_BACKEND_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

/** Credentials. OSS defaults are the seeded dev pair; auth0 needs real ones. */
const USERNAME =
  process.env.UNSTRACT_ADMIN_USER ??
  process.env.UNSTRACT_AUTH0_USER ??
  "unstract";
const PASSWORD =
  process.env.UNSTRACT_ADMIN_PASSWORD ??
  process.env.UNSTRACT_AUTH0_PASSWORD ??
  "unstract";

/**
 * Fetch the org id from the API. Also the OSS liveness probe: a 401 here means
 * the session did not take, which is exactly how a cloud-auth backend behaves
 * when handed OSS mock-login credentials.
 */
async function fetchOrgId(context) {
  const res = await context.request
    .get(`${BACKEND}/api/v1/organization`, { failOnStatusCode: false })
    .catch(() => null);
  if (!res?.ok()) {
    return null;
  }
  return (await res.json())?.organizations?.[0]?.id ?? null;
}

/** OSS mock-login: form POST, then set the active organization. */
async function loginOss(context) {
  const login = await context.request
    .post(`${BACKEND}/api/v1/login`, {
      form: { username: USERNAME, password: PASSWORD },
      maxRedirects: 0,
      failOnStatusCode: false,
    })
    .catch(() => null);
  // 200 means the login form re-rendered: bad credentials.
  if (login?.status() !== 302) {
    return null;
  }

  const orgId = await fetchOrgId(context);
  if (!orgId) {
    return null;
  }

  const csrf = (await context.cookies()).find((c) => c.name === "csrftoken")
    ?.value;
  await context.request.post(`${BACKEND}/api/v1/organization/${orgId}/set`, {
    headers: csrf ? { "X-CSRFToken": csrf } : {},
    failOnStatusCode: false,
  });
  return orgId;
}

/**
 * Auth0: drive the hosted login form in a real browser.
 *
 * The IdP owns the credential exchange and sets its own cookies across a
 * redirect chain, so this cannot be done over the request API. Navigating to
 * the app root triggers the redirect to Auth0; filling the form there returns
 * through the app's callback with a session.
 */
async function loginAuth0(page, context) {
  await page.goto("/", { waitUntil: "domcontentloaded" }).catch(() => {});

  // Field names are stable across Auth0's templates (Universal Login and the
  // classic Lock widget).
  const user = page
    .locator('input[name="username"], input[name="email"], input#username')
    .first();
  if (!(await user.count())) {
    // Already authenticated (reused storage state), or not an Auth0 screen.
    return await fetchOrgId(context);
  }

  await user.fill(USERNAME);
  await page
    .locator('input[name="password"], input#password')
    .first()
    .fill(PASSWORD);
  await page
    .locator('button[type="submit"], button[name="action"]')
    .first()
    .click();

  // The callback bounces through the app; wait for it to settle rather than
  // guessing at a landing URL, which differs by tenant config.
  await page.waitForLoadState("networkidle").catch(() => {});
  return await fetchOrgId(context);
}

/** Resolve the auth mode, honouring an explicit override. */
function authMode() {
  const explicit = process.env.UNSTRACT_AUTH_MODE?.toLowerCase();
  return explicit === "oss" || explicit === "auth0" ? explicit : "auto";
}

async function authenticate(page, context) {
  const mode = authMode();

  if (mode === "oss" || mode === "auto") {
    const orgId = await loginOss(context);
    if (orgId) {
      return { orgId, mode: "oss" };
    }
    if (mode === "oss") {
      return { orgId: null, mode: "oss" };
    }
    // auto: OSS mock-login did not take — fall through to auth0.
  }

  const orgId = await loginAuth0(page, context);
  return { orgId, mode: "auth0" };
}

export const test = base.extend({
  /** `app.goto(route)` — navigate to an org-scoped route, or skip. */
  app: async ({ page, context }, use) => {
    const { orgId, mode } = await authenticate(page, context);
    await use({
      orgId,
      authMode: mode,
      async goto(route) {
        test.skip(
          !orgId,
          `could not authenticate against ${BACKEND} (mode=${mode}). ` +
            "Set UNSTRACT_AUTH_MODE=oss|auth0 plus credentials, or let the " +
            "rig boot a stack (`python -m tests.rig run ui`).",
        );
        const response = await page.goto(`/${orgId}/${route}`, {
          waitUntil: "domcontentloaded",
        });
        // The SPA renders after hydration; wait for the shell rather than a
        // fixed timeout so slow CI does not flake.
        await page.waitForLoadState("networkidle").catch(() => {});
        return response;
      },
    });
  },
});

export { expect };
